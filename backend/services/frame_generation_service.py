from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.ai.frame_prompt_builder import (
    build_frame_base_instructions,
    build_frame_generation_prompt,
    extract_frame_content,
    frame_render_tool,
)
from backend.ai.split_context_builder import build_split_context
from backend.errors.app_errors import (
    FrameGenerationBackendUnavailable,
    FrameGenerationNotAllowed,
    NodeNotFound,
    ProjectNotFound,
)
from backend.services import planningtree_workspace
from backend.services.tree_service import TreeService
from backend.storage.file_utils import atomic_write_json, iso_now, load_json, new_id
from backend.storage.storage import Storage

logger = logging.getLogger(__name__)

FRAME_GEN_STATE_FILE = "frame_gen.json"

_STALE_JOB_MESSAGE = "Frame generation was interrupted because the server restarted before it completed."


def _default_gen_state() -> dict[str, Any]:
    return {
        "thread_id": None,
        "active_job": None,
        "last_error": None,
        "last_completed_at": None,
    }


class FrameGenerationService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        codex_client: CodexAppClient,
        frame_gen_timeout: int,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._codex_client = codex_client
        self._timeout = int(frame_gen_timeout)
        self._live_jobs_lock = threading.Lock()
        self._live_jobs: dict[str, str] = {}  # keyed by "project_id::node_id"

    # ── Public API ─────────────────────────────────────────────────

    def generate_frame(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)

            node_dir = self._resolve_node_dir(snapshot, node_id)
            gen_state = self._reconcile_stale_job(project_id, node_id, node_dir)

            if gen_state.get("active_job"):
                raise FrameGenerationNotAllowed(
                    "Frame generation is already in progress for this node."
                )

            workspace_root = self._workspace_root_from_snapshot(snapshot)

        # Ensure generation thread (outside project lock — may do network I/O)
        gen_state = self._load_gen_state(node_dir)
        existing_thread_id = gen_state.get("thread_id")
        thread_id = self._ensure_gen_thread(existing_thread_id, workspace_root)

        job_id = new_id("fgen")
        started_at = iso_now()
        job_key = self._job_key(project_id, node_id)

        with self._storage.project_lock(project_id):
            # Re-read to guard against races
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            gen_state = self._reconcile_stale_job(project_id, node_id, node_dir)
            if gen_state.get("active_job"):
                raise FrameGenerationNotAllowed(
                    "Frame generation is already in progress for this node."
                )

            gen_state["thread_id"] = thread_id
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
                "job_id": job_id,
                "started_at": started_at,
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
        job_id: str,
        started_at: str,
    ) -> None:
        try:
            content = self._generate_frame_content(project_id, node_id)
            self._write_frame_content(project_id, node_id, content)
            self._mark_job_completed(project_id, node_id, job_id)
        except ProjectNotFound:
            self._clear_live_job(project_id, node_id, job_id)
        except Exception as exc:
            logger.debug(
                "Frame generation failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )
            self._mark_job_failed(project_id, node_id, job_id, started_at, str(exc))

    def _generate_frame_content(self, project_id: str, node_id: str) -> str:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)

            node_dir = self._resolve_node_dir(snapshot, node_id)
            gen_state = self._load_gen_state(node_dir)
            thread_id = str(gen_state.get("thread_id") or "").strip()
            if not thread_id:
                raise FrameGenerationBackendUnavailable(
                    "Generation thread is unavailable. Retry the generation."
                )

            workspace_root = self._workspace_root_from_snapshot(snapshot)
            task_context = build_split_context(snapshot, node, node_by_id)

            # Read chat history for this node
            chat_session = self._storage.chat_state_store.read_session(
                project_id, node_id
            )
            chat_messages = chat_session.get("messages", [])

        # Build prompt and run turn (outside lock)
        prompt = build_frame_generation_prompt(chat_messages, task_context)
        result = self._codex_client.run_turn_streaming(
            prompt,
            thread_id=thread_id,
            timeout_sec=self._timeout,
            cwd=workspace_root,
        )

        tool_calls = result.get("tool_calls", [])
        content = extract_frame_content(tool_calls)
        if content:
            return content

        # Fallback: use stdout if no tool call
        stdout = str(result.get("stdout", "") or "").strip()
        if stdout:
            return stdout

        raise FrameGenerationBackendUnavailable(
            "AI did not produce frame content. Retry the generation."
        )

    def _write_frame_content(
        self, project_id: str, node_id: str, content: str
    ) -> None:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
            frame_path.write_text(content, encoding="utf-8")

            # Bump frame revision so confirm_frame picks up a new revision,
            # matching the behavior of the normal save path (PUT /documents/frame).
            from backend.services.node_detail_service import FRAME_META_FILE, _DEFAULT_FRAME_META
            meta_path = node_dir / FRAME_META_FILE
            meta = load_json(meta_path, default=None)
            if not isinstance(meta, dict):
                meta = dict(_DEFAULT_FRAME_META)
            meta["revision"] = (meta.get("revision") or 0) + 1
            atomic_write_json(meta_path, meta)

    # ── Thread management ──────────────────────────────────────────

    def _ensure_gen_thread(
        self, existing_thread_id: Any, workspace_root: str | None
    ) -> str:
        if isinstance(existing_thread_id, str) and existing_thread_id.strip():
            try:
                self._codex_client.resume_thread(
                    existing_thread_id,
                    cwd=workspace_root,
                    timeout_sec=15,
                )
                return existing_thread_id.strip()
            except CodexTransportError as exc:
                if not self._is_missing_thread_error(exc):
                    raise FrameGenerationBackendUnavailable(str(exc)) from exc

        try:
            response = self._codex_client.start_thread(
                base_instructions=build_frame_base_instructions(),
                dynamic_tools=[frame_render_tool()],
                cwd=workspace_root,
                timeout_sec=30,
            )
        except CodexTransportError as exc:
            raise FrameGenerationBackendUnavailable(str(exc)) from exc

        thread_id = str(response.get("thread_id") or "").strip()
        if not thread_id:
            raise FrameGenerationBackendUnavailable(
                "Generation thread start did not return a thread id."
            )
        return thread_id

    # ── State persistence ──────────────────────────────────────────

    def _load_gen_state(self, node_dir: Path) -> dict[str, Any]:
        path = node_dir / FRAME_GEN_STATE_FILE
        payload = load_json(path, default=None)
        if not isinstance(payload, dict):
            return _default_gen_state()
        return payload

    def _save_gen_state(self, node_dir: Path, state: dict[str, Any]) -> None:
        path = node_dir / FRAME_GEN_STATE_FILE
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

    def has_live_jobs_for_project(self, project_id: str) -> bool:
        prefix = f"{project_id}::"
        with self._live_jobs_lock:
            return any(key.startswith(prefix) for key in self._live_jobs)

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

    def _is_missing_thread_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return (
            "no rollout found for thread id" in message
            or "thread not found" in message
        )
