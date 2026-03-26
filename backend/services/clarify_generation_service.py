from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from backend.ai.ask_thread_config import build_ask_planning_thread_config
from backend.ai.clarify_prompt_builder import (
    build_clarify_generation_prompt,
    extract_clarify_questions,
    extract_clarify_questions_from_text,
)
from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.ai.split_context_builder import build_split_context
from backend.errors.app_errors import (
    ClarifyGenerationBackendUnavailable,
    ClarifyGenerationNotAllowed,
    NodeNotFound,
    ProjectNotFound,
)
from backend.services import planningtree_workspace
from backend.services.execution_gating import require_shaping_not_frozen
from backend.services.thread_lineage_service import ThreadLineageService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import atomic_write_json, iso_now, load_json, new_id
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)

CLARIFY_GEN_STATE_FILE = "clarify_gen.json"

_STALE_JOB_MESSAGE = (
    "Clarify generation was interrupted because the server restarted before it completed."
)


def _default_gen_state() -> dict[str, Any]:
    return {
        "active_job": None,
        "last_error": None,
        "last_completed_at": None,
    }


class ClarifyGenerationService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        codex_client: CodexAppClient,
        thread_lineage_service: ThreadLineageService,
        clarify_gen_timeout: int,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._codex_client = codex_client
        self._thread_lineage_service = thread_lineage_service
        self._timeout = int(clarify_gen_timeout)
        self._live_jobs_lock = threading.Lock()
        self._live_jobs: dict[str, str] = {}

    # ── Public API ─────────────────────────────────────────────────

    def generate_clarify(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            require_shaping_not_frozen(self._storage, project_id, node_id, "generate clarify")

            node_dir = self._resolve_node_dir(snapshot, node_id)
            gen_state = self._reconcile_stale_job(project_id, node_id, node_dir)

            if gen_state.get("active_job"):
                raise ClarifyGenerationNotAllowed(
                    "Clarify generation is already in progress for this node."
                )

            workspace_root = self._workspace_root_from_snapshot(snapshot)

        # Ensure generation thread (outside project lock — may do network I/O)
        thread_id = self._ensure_ask_thread(project_id, node_id, workspace_root)

        job_id = new_id("cgen")
        started_at = iso_now()

        with self._storage.project_lock(project_id):
            # Re-read to guard against races
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            gen_state = self._reconcile_stale_job(project_id, node_id, node_dir)
            if gen_state.get("active_job"):
                raise ClarifyGenerationNotAllowed(
                    "Clarify generation is already in progress for this node."
                )

            # Read confirmed frame content from sidecar (snapshotted at confirm
            # time), not from frame.md which may contain post-confirm draft edits.
            # Fallback: nodes confirmed before the confirmed_content field was added
            # won't have it — read frame.md as best-effort for migration.
            from backend.services.node_detail_service import FRAME_META_FILE, _DEFAULT_FRAME_META
            meta_path = node_dir / FRAME_META_FILE
            frame_meta = load_json(meta_path, default=None)
            if not isinstance(frame_meta, dict):
                frame_meta = dict(_DEFAULT_FRAME_META)
            frame_content = str(frame_meta.get("confirmed_content") or "")
            if not frame_content:
                frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
                if frame_path.exists():
                    frame_content = frame_path.read_text(encoding="utf-8")

            source_frame_revision = frame_meta.get("confirmed_revision", 0)
            frame_revision_at_start = frame_meta.get("revision", 0)

            gen_state["active_job"] = {
                "job_id": job_id,
                "started_at": started_at,
            }
            gen_state["last_error"] = None
            self._save_gen_state(node_dir, gen_state)
            self._mark_live_job(project_id, node_id, job_id)

        threading.Thread(
            target=self._run_background_generation,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "thread_id": thread_id,
                "job_id": job_id,
                "started_at": started_at,
                "frame_content": frame_content,
                "source_frame_revision": source_frame_revision,
                "frame_revision_at_start": frame_revision_at_start,
            },
            daemon=True,
        ).start()

        return {
            "status": "accepted",
            "job_id": job_id,
            "node_id": node_id,
        }

    def get_generation_status(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            if node_id not in node_by_id:
                raise NodeNotFound(node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            gen_state = self._reconcile_stale_job(project_id, node_id, node_dir)
            return self._status_payload(gen_state)

    # ── Background generation ──────────────────────────────────────

    def _run_background_generation(
        self,
        *,
        project_id: str,
        node_id: str,
        thread_id: str,
        job_id: str,
        started_at: str,
        frame_content: str,
        source_frame_revision: int,
        frame_revision_at_start: int = 0,
    ) -> None:
        try:
            questions = self._generate_clarify_questions(
                project_id,
                node_id,
                thread_id,
                frame_content,
            )
            self._write_clarify_content(
                project_id, node_id, questions, source_frame_revision, frame_revision_at_start
            )
            self._mark_job_completed(project_id, node_id, job_id)
        except ProjectNotFound:
            self._clear_live_job(project_id, node_id, job_id)
        except Exception as exc:
            logger.debug(
                "Clarify generation failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )
            self._mark_job_failed(project_id, node_id, job_id, started_at, str(exc))

    def _generate_clarify_questions(
        self,
        project_id: str,
        node_id: str,
        thread_id: str,
        frame_content: str,
    ) -> list[dict[str, Any]]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)

            workspace_root = self._workspace_root_from_snapshot(snapshot)
            task_context = build_split_context(snapshot, node, node_by_id)

        # Build prompt using snapshotted frame content (captured at job start)
        prompt = build_clarify_generation_prompt(frame_content, task_context)
        result = self._codex_client.run_turn_streaming(
            prompt,
            thread_id=thread_id,
            timeout_sec=self._timeout,
            cwd=workspace_root,
        )

        tool_calls = result.get("tool_calls", [])
        questions = extract_clarify_questions(tool_calls)
        if questions is not None:
            return questions

        # Fallback: try parsing stdout as JSON
        stdout = str(result.get("stdout", "") or "").strip()
        if stdout:
            questions = extract_clarify_questions_from_text(stdout)
            if questions is not None:
                return questions

        raise ClarifyGenerationBackendUnavailable(
            "AI did not produce clarify questions. Retry the generation."
        )

    def _write_clarify_content(
        self,
        project_id: str,
        node_id: str,
        questions: list[dict[str, Any]],
        source_frame_revision: int,
        frame_revision_at_start: int = 0,
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)

            # Stale-job guard 1: if frame was re-confirmed while this job ran,
            # the on-disk clarify may have been re-seeded with a newer
            # source_frame_revision. Skip writing to avoid overwriting it.
            from backend.services.node_detail_service import CLARIFY_FILE, FRAME_META_FILE
            clarify_path = node_dir / CLARIFY_FILE
            existing = load_json(clarify_path, default=None)
            if isinstance(existing, dict):
                disk_rev = existing.get("source_frame_revision", 0)
                if disk_rev > source_frame_revision:
                    logger.warning(
                        "Stale clarify generation for %s/%s: job source_frame_revision=%d "
                        "< disk source_frame_revision=%d — skipping write.",
                        project_id,
                        node_id,
                        source_frame_revision,
                        disk_rev,
                    )
                    return

                # Guard 2: on-disk clarify already confirmed (zero-question auto-confirm)
                disk_confirmed_rev = existing.get("confirmed_revision", 0)
                if disk_confirmed_rev > 0:
                    logger.warning(
                        "Stale clarify generation for %s/%s: on-disk clarify already confirmed "
                        "(confirmed_revision=%d) — skipping AI write.",
                        project_id,
                        node_id,
                        disk_confirmed_rev,
                    )
                    return

            # Guard 3: frame draft changed since job started (apply-to-frame bumped revision)
            if frame_revision_at_start > 0:
                frame_meta_path = node_dir / FRAME_META_FILE
                current_frame_meta = load_json(frame_meta_path, default=None)
                if isinstance(current_frame_meta, dict):
                    current_frame_rev = current_frame_meta.get("revision", 0)
                    if current_frame_rev > frame_revision_at_start:
                        logger.warning(
                            "Stale clarify generation for %s/%s: frame revision advanced "
                            "(%d > %d) since job started — skipping AI write.",
                            project_id,
                            node_id,
                            current_frame_rev,
                            frame_revision_at_start,
                        )
                        return

            # Preserve existing selections if re-generating
            if isinstance(existing, dict):
                old_by_field = {
                    q["field_name"]: q
                    for q in existing.get("questions", [])
                    if isinstance(q, dict)
                }
                for q in questions:
                    old = old_by_field.get(q["field_name"])
                    if old:
                        # Always preserve custom_answer
                        q["custom_answer"] = old.get("custom_answer", "")
                        # Preserve selected_option_id only if option still exists
                        old_selected = old.get("selected_option_id")
                        if old_selected is not None:
                            new_option_ids = {
                                o["id"] for o in q.get("options", [])
                                if isinstance(o, dict) and "id" in o
                            }
                            if old_selected in new_option_ids:
                                q["selected_option_id"] = old_selected

            # Zero questions = auto-confirm per workflow contract
            now = iso_now()
            auto_confirm = len(questions) == 0
            clarify: dict[str, Any] = {
                "schema_version": 2,
                "source_frame_revision": source_frame_revision,
                "confirmed_revision": 1 if auto_confirm else 0,
                "confirmed_at": now if auto_confirm else None,
                "questions": questions,
                "updated_at": now,
            }
            atomic_write_json(clarify_path, clarify)

    # ── Thread management ──────────────────────────────────────────

    def _ensure_ask_thread(self, project_id: str, node_id: str, workspace_root: str | None) -> str:
        base_instructions, dynamic_tools = build_ask_planning_thread_config()
        try:
            session = self._thread_lineage_service.ensure_forked_thread(
                project_id,
                node_id,
                "ask_planning",
                source_node_id=node_id,
                source_role="audit",
                fork_reason="ask_bootstrap",
                workspace_root=workspace_root,
                base_instructions=base_instructions,
                dynamic_tools=dynamic_tools,
            )
        except CodexTransportError as exc:
            raise ClarifyGenerationBackendUnavailable(str(exc)) from exc

        thread_id = str(session.get("thread_id") or "").strip()
        if not thread_id:
            raise ClarifyGenerationBackendUnavailable(
                "Ask thread bootstrap did not return a thread id."
            )
        return thread_id

    # ── State persistence ──────────────────────────────────────────

    def _load_gen_state(self, node_dir: Path) -> dict[str, Any]:
        path = node_dir / CLARIFY_GEN_STATE_FILE
        payload = load_json(path, default=None)
        if not isinstance(payload, dict):
            return _default_gen_state()
        return {
            "active_job": payload.get("active_job"),
            "last_error": payload.get("last_error"),
            "last_completed_at": payload.get("last_completed_at"),
        }

    def _save_gen_state(self, node_dir: Path, state: dict[str, Any]) -> None:
        path = node_dir / CLARIFY_GEN_STATE_FILE
        atomic_write_json(path, state)

    def _reconcile_stale_job(
        self, project_id: str, node_id: str, node_dir: Path
    ) -> dict[str, Any]:
        gen_state = self._load_gen_state(node_dir)
        active_job = gen_state.get("active_job")
        if not isinstance(active_job, dict):
            return gen_state
        job_id = active_job.get("job_id")
        if not isinstance(job_id, str) or not job_id.strip():
            gen_state["active_job"] = None
            self._save_gen_state(node_dir, gen_state)
            return gen_state
        if self._is_live_job(project_id, node_id, job_id):
            return gen_state

        # Stale job — server restarted
        gen_state["active_job"] = None
        gen_state["last_error"] = {
            "job_id": job_id,
            "started_at": active_job.get("started_at"),
            "completed_at": iso_now(),
            "error": _STALE_JOB_MESSAGE,
        }
        self._save_gen_state(node_dir, gen_state)
        return gen_state

    def _status_payload(self, gen_state: dict[str, Any]) -> dict[str, Any]:
        active_job = gen_state.get("active_job")
        if isinstance(active_job, dict):
            return {
                "status": "active",
                "job_id": active_job.get("job_id"),
                "started_at": active_job.get("started_at"),
                "completed_at": None,
                "error": None,
            }

        last_error = gen_state.get("last_error")
        if isinstance(last_error, dict):
            return {
                "status": "failed",
                "job_id": last_error.get("job_id"),
                "started_at": last_error.get("started_at"),
                "completed_at": last_error.get("completed_at"),
                "error": last_error.get("error"),
            }

        return {
            "status": "idle",
            "job_id": None,
            "started_at": None,
            "completed_at": None,
            "error": None,
        }

    def _mark_job_completed(
        self, project_id: str, node_id: str, job_id: str
    ) -> None:
        try:
            with self._storage.project_lock(project_id):
                snapshot = self._storage.project_store.load_snapshot(project_id)
                node_dir = self._resolve_node_dir(snapshot, node_id)
                gen_state = self._load_gen_state(node_dir)
                active_job = gen_state.get("active_job")
                if isinstance(active_job, dict) and active_job.get("job_id") == job_id:
                    gen_state["active_job"] = None
                    gen_state["last_error"] = None
                    gen_state["last_completed_at"] = iso_now()
                    self._save_gen_state(node_dir, gen_state)
        finally:
            self._clear_live_job(project_id, node_id, job_id)

    def _mark_job_failed(
        self,
        project_id: str,
        node_id: str,
        job_id: str,
        started_at: str,
        message: str,
    ) -> None:
        try:
            with self._storage.project_lock(project_id):
                snapshot = self._storage.project_store.load_snapshot(project_id)
                node_dir = self._resolve_node_dir(snapshot, node_id)
                gen_state = self._load_gen_state(node_dir)
                active_job = gen_state.get("active_job")
                if isinstance(active_job, dict) and active_job.get("job_id") == job_id:
                    gen_state["active_job"] = None
                gen_state["last_error"] = {
                    "job_id": job_id,
                    "started_at": started_at,
                    "completed_at": iso_now(),
                    "error": message,
                }
                self._save_gen_state(node_dir, gen_state)
        except ProjectNotFound:
            pass
        finally:
            self._clear_live_job(project_id, node_id, job_id)

    # ── Live job tracking ──────────────────────────────────────────

    def _job_key(self, project_id: str, node_id: str) -> str:
        return f"{project_id}::{node_id}"

    def _mark_live_job(
        self, project_id: str, node_id: str, job_id: str
    ) -> None:
        with self._live_jobs_lock:
            self._live_jobs[self._job_key(project_id, node_id)] = job_id

    def _clear_live_job(
        self, project_id: str, node_id: str, job_id: str
    ) -> None:
        key = self._job_key(project_id, node_id)
        with self._live_jobs_lock:
            if self._live_jobs.get(key) == job_id:
                self._live_jobs.pop(key, None)

    def _is_live_job(
        self, project_id: str, node_id: str, job_id: str
    ) -> bool:
        with self._live_jobs_lock:
            return self._live_jobs.get(self._job_key(project_id, node_id)) == job_id

    # ── Helpers ────────────────────────────────────────────────────

    def _resolve_node_dir(self, snapshot: dict[str, Any], node_id: str) -> Path:
        project = snapshot.get("project", {})
        raw_path = str(project.get("project_path") or "").strip()
        if not raw_path:
            raise NodeNotFound(node_id)
        project_path = Path(raw_path)
        node_dir = planningtree_workspace.resolve_node_dir(
            project_path, snapshot, node_id
        )
        if node_dir is None:
            raise NodeNotFound(node_id)
        return node_dir

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str | None:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            return None
        workspace_root = project.get("project_path")
        if isinstance(workspace_root, str) and workspace_root.strip():
            return workspace_root
        return None
