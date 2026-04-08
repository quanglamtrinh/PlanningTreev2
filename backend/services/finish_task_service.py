from __future__ import annotations

import logging
import re
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from backend.ai.auto_review_prompt_builder import (
    build_auto_review_base_instructions,
    build_auto_review_output_schema,
    build_auto_review_prompt,
    extract_auto_review_result,
)
from backend.ai.codex_client import CodexAppClient
from backend.conversation.services.thread_runtime_service import ThreadRuntimeService
from backend.conversation.services.workflow_event_publisher import WorkflowEventPublisher
from backend.ai.execution_prompt_builder import (
    build_execution_base_instructions,
    build_execution_prompt,
)
from backend.ai.part_accumulator import PartAccumulator
from backend.ai.split_context_builder import build_split_context
from backend.errors.app_errors import (
    ChatTurnAlreadyActive,
    ExecutionAuditRehearsalWorkspaceUnsafe,
    FinishTaskNotAllowed,
    NodeNotFound,
)
from backend.services import planningtree_workspace
from backend.services.execution_file_change_hydrator import (
    ExecutionFileChangeDiffSource,
    ExecutionFileChangeHydrator,
)
from backend.services.node_detail_service import (
    NodeDetailService,
    _DEFAULT_FRAME_META,
    _load_spec_meta_from_node_dir,
)
from backend.services.thread_lineage_service import ThreadLineageService
from backend.services.tree_service import TreeService
from backend.storage.file_utils import iso_now, load_json, new_id
from backend.storage.storage import Storage
from backend.streaming.sse_broker import ChatEventBroker

logger = logging.getLogger(__name__)

_DRAFT_FLUSH_INTERVAL_SEC = 0.5
_LIVE_FILE_CHANGE_HYDRATE_DEBOUNCE_SEC = 0.35

if TYPE_CHECKING:
    from backend.services.chat_service import ChatService
    from backend.services.review_service import ReviewService


class FinishTaskService:
    def __init__(
        self,
        storage: Storage,
        tree_service: TreeService,
        node_detail_service: NodeDetailService,
        codex_client: CodexAppClient,
        thread_lineage_service: ThreadLineageService,
        chat_event_broker: ChatEventBroker,
        chat_timeout: int,
        chat_service: ChatService | None = None,
        git_checkpoint_service: Any = None,
        review_service: ReviewService | None = None,
        thread_runtime_service_v2: ThreadRuntimeService | None = None,
        workflow_event_publisher_v2: WorkflowEventPublisher | None = None,
        execution_audit_v2_enabled: bool = False,
        execution_audit_v2_rehearsal_enabled: bool = False,
        rehearsal_workspace_root: Path | None = None,
    ) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._node_detail_service = node_detail_service
        self._codex_client = codex_client
        self._thread_lineage_service = thread_lineage_service
        self._chat_event_broker = chat_event_broker
        self._chat_timeout = int(chat_timeout)
        self._chat_service = chat_service
        self._git_checkpoint_service = git_checkpoint_service
        self._review_service = review_service
        self._thread_runtime_service_v2 = thread_runtime_service_v2
        self._workflow_event_publisher_v2 = workflow_event_publisher_v2
        self._execution_audit_v2_enabled = bool(execution_audit_v2_enabled)
        self._execution_audit_v2_rehearsal_enabled = bool(execution_audit_v2_rehearsal_enabled)
        self._rehearsal_workspace_root = (
            Path(rehearsal_workspace_root).expanduser().resolve()
            if rehearsal_workspace_root is not None
            else None
        )
        self._live_jobs_lock = threading.Lock()
        self._live_jobs: dict[str, str] = {}

    def finish_task(self, project_id: str, node_id: str) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_index = snapshot.get("tree_state", {}).get("node_index", {})
            node = node_index.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)

            node_dir = self._resolve_node_dir(snapshot, node_id)
            spec_content = self._validate_finish_task_locked(project_id, node_id, snapshot, node, node_dir)
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            frame_content = self._load_confirmed_frame_content(node_dir)
            task_context = build_split_context(snapshot, node, node_index)
        v2_mode = self._execution_audit_v2_mode()
        if v2_mode == "production":
            return self._finish_task_v2(
                project_id=project_id,
                node_id=node_id,
                spec_content=spec_content,
                frame_content=frame_content,
                task_context=task_context,
                workspace_root=workspace_root,
                node=node,
                enforce_rehearsal_workspace=False,
                enable_auto_review=True,
            )
        if self._execution_audit_v2_rehearsal_enabled:
            return self._finish_task_v2_rehearsal(
                project_id=project_id,
                node_id=node_id,
                spec_content=spec_content,
                frame_content=frame_content,
                task_context=task_context,
                workspace_root=workspace_root,
                node=node,
            )
        execution_session = self._ensure_execution_thread(project_id, node_id, workspace_root)
        thread_id = str(execution_session.get("thread_id") or "").strip()
        if not thread_id:
            raise FinishTaskNotAllowed("Execution bootstrap did not return a thread id.")

        turn_id = new_id("exec")
        assistant_message_id = new_id("msg")
        now = iso_now()
        assistant_message = {
            "message_id": assistant_message_id,
            "role": "assistant",
            "content": "",
            "status": "pending",
            "error": None,
            "turn_id": turn_id,
            "created_at": now,
            "updated_at": now,
        }
        prompt = build_execution_prompt(
            spec_content=spec_content,
            frame_content=frame_content,
            task_context=task_context,
        )
        initial_sha: str

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_index = snapshot.get("tree_state", {}).get("node_index", {})
            node = node_index.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            node_dir = self._resolve_node_dir(snapshot, node_id)
            self._validate_finish_task_locked(project_id, node_id, snapshot, node, node_dir)
            initial_sha = self._compute_initial_sha(project_id, node_id, snapshot)

            exec_state = {
                "status": "executing",
                "initial_sha": initial_sha,
                "head_sha": None,
                "started_at": now,
                "completed_at": None,
                "local_review_started_at": None,
                "local_review_prompt_consumed_at": None,
            }
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            if node.get("status") != "in_progress":
                node["status"] = "in_progress"
                snapshot["updated_at"] = now
                self._storage.project_store.save_snapshot(project_id, snapshot)

            session = self._storage.chat_state_store.read_session(
                project_id,
                node_id,
                thread_role="execution",
            )
            session["thread_id"] = thread_id
            session["active_turn_id"] = turn_id
            session["messages"] = [assistant_message]
            self._storage.chat_state_store.write_session(
                project_id,
                node_id,
                session,
                thread_role="execution",
            )
            self._mark_live_job(project_id, node_id, turn_id)

        self._chat_event_broker.publish(
            project_id,
            node_id,
            {
                "type": "message_created",
                "assistant_message": assistant_message,
                "active_turn_id": turn_id,
            },
            thread_role="execution",
        )

        # Resolve hierarchical_number and title for commit message
        h_number = str(node.get("hierarchical_number") or "")
        title = str(node.get("title") or "")

        threading.Thread(
            target=self._run_background_execution,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "assistant_message_id": assistant_message_id,
                "thread_id": thread_id,
                "prompt": prompt,
                "workspace_root": workspace_root,
                "initial_sha": initial_sha,
                "hierarchical_number": h_number,
                "title": title,
            },
            daemon=True,
        ).start()

        return self._node_detail_service.get_detail_state(project_id, node_id)

    def _execution_audit_v2_mode(self) -> str | None:
        if self._execution_audit_v2_enabled:
            return "production"
        if self._execution_audit_v2_rehearsal_enabled:
            return "rehearsal"
        return None

    def _finish_task_v2(
        self,
        *,
        project_id: str,
        node_id: str,
        spec_content: str,
        frame_content: str,
        task_context: str,
        workspace_root: str | None,
        node: dict[str, Any],
        enforce_rehearsal_workspace: bool,
        enable_auto_review: bool,
    ) -> dict[str, Any]:
        if self._thread_runtime_service_v2 is None:
            raise FinishTaskNotAllowed("Execution V2 runtime is unavailable.")
        if enforce_rehearsal_workspace:
            self._assert_rehearsal_workspace_allowed(workspace_root)
        thread_id = self._ensure_execution_thread_id_v2(project_id, node_id, workspace_root)

        turn_id = new_id("exec")
        prompt = build_execution_prompt(
            spec_content=spec_content,
            frame_content=frame_content,
            task_context=task_context,
        )
        now = iso_now()
        initial_sha: str

        self._thread_runtime_service_v2.begin_turn(
            project_id=project_id,
            node_id=node_id,
            thread_role="execution",
            origin="execution",
            created_items=[],
            turn_id=turn_id,
        )

        try:
            with self._storage.project_lock(project_id):
                snapshot = self._storage.project_store.load_snapshot(project_id)
                node_index = snapshot.get("tree_state", {}).get("node_index", {})
                current_node = node_index.get(node_id)
                if current_node is None:
                    raise NodeNotFound(node_id)
                node_dir = self._resolve_node_dir(snapshot, node_id)
                self._validate_finish_task_locked(project_id, node_id, snapshot, current_node, node_dir)
                initial_sha = self._compute_initial_sha(project_id, node_id, snapshot)

                exec_state = {
                    "status": "executing",
                    "initial_sha": initial_sha,
                    "head_sha": None,
                    "started_at": now,
                    "completed_at": None,
                    "local_review_started_at": None,
                    "local_review_prompt_consumed_at": None,
                }
                self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

                if current_node.get("status") != "in_progress":
                    current_node["status"] = "in_progress"
                    snapshot["updated_at"] = now
                    self._storage.project_store.save_snapshot(project_id, snapshot)

                self._mark_live_job(project_id, node_id, turn_id)
        except Exception as exc:
            error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                turn_id=turn_id,
                thread_id=thread_id,
                message=str(exc),
            )
            self._thread_runtime_service_v2.complete_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                turn_id=turn_id,
                outcome="failed",
                error_item=error_item,
            )
            raise

        self._publish_workflow_refresh(
            project_id=project_id,
            node_id=node_id,
            reason="execution_started",
        )

        threading.Thread(
            target=self._run_background_execution_v2,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "thread_id": thread_id,
                "prompt": prompt,
                "workspace_root": workspace_root,
                "initial_sha": initial_sha,
                "hierarchical_number": str(node.get("hierarchical_number") or ""),
                "title": str(node.get("title") or ""),
                "enable_auto_review": enable_auto_review,
            },
            daemon=True,
        ).start()

        return self._node_detail_service.get_detail_state(project_id, node_id)

    def _finish_task_v2_rehearsal(
        self,
        *,
        project_id: str,
        node_id: str,
        spec_content: str,
        frame_content: str,
        task_context: str,
        workspace_root: str | None,
        node: dict[str, Any],
    ) -> dict[str, Any]:
        return self._finish_task_v2(
            project_id=project_id,
            node_id=node_id,
            spec_content=spec_content,
            frame_content=frame_content,
            task_context=task_context,
            workspace_root=workspace_root,
            node=node,
            enforce_rehearsal_workspace=True,
            enable_auto_review=False,
        )

    def complete_execution(
        self,
        project_id: str,
        node_id: str,
        head_sha: str | None = None,
        commit_message: str | None = None,
        changed_files: list[dict[str, Any]] | None = None,
        *,
        publish_legacy_event: bool = True,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None:
                raise FinishTaskNotAllowed("No execution state exists for this node.")
            if exec_state.get("status") != "executing":
                raise FinishTaskNotAllowed(
                    f"Cannot complete execution: status is '{exec_state.get('status')}', expected 'executing'."
                )

            exec_state["status"] = "completed"
            exec_state["head_sha"] = head_sha
            exec_state["completed_at"] = iso_now()
            if commit_message is not None:
                exec_state["commit_message"] = commit_message
            if changed_files is not None:
                exec_state["changed_files"] = changed_files
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

        detail_state = self._node_detail_service.get_detail_state(project_id, node_id)
        if publish_legacy_event:
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "execution_completed",
                    "node_id": node_id,
                    "head_sha": head_sha,
                    "execution_status": "completed",
                },
                thread_role="execution",
            )
        return detail_state

    @staticmethod
    def _looks_like_structured_diff(text: str | None) -> bool:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            return False
        return (
            "diff --git " in normalized
            or "*** Begin Patch" in normalized
            or "\n@@ " in f"\n{normalized}"
            or "\n+++ " in f"\n{normalized}"
            or "\n--- " in f"\n{normalized}"
        )

    @staticmethod
    def _normalize_path_for_diff_match(path: str | None) -> str:
        candidate = str(path or "").replace("\\", "/").strip()
        if not candidate:
            return ""
        if len(candidate) >= 2 and candidate[1] == ":":
            candidate = candidate[2:]
        candidate = candidate.lstrip("/")
        candidate = re.sub(r"^\./+", "", candidate)
        return candidate.lower()

    @staticmethod
    def _is_planningtree_path(path: str | None) -> bool:
        normalized = FinishTaskService._normalize_path_for_diff_match(path)
        return normalized == ".planningtree" or normalized.startswith(".planningtree/")

    @staticmethod
    def _strip_git_ab_prefix(path: str) -> str:
        candidate = str(path or "").strip().replace("\\", "/")
        if candidate.startswith(("a/", "b/")) and len(candidate) > 2:
            return candidate[2:]
        return candidate

    @staticmethod
    def _extract_paths_from_diff_git_header(line: str) -> list[str]:
        payload = line[len("diff --git ") :].strip()
        if not payload:
            return []
        paths: list[str] = []
        rest = payload
        while rest:
            if rest.startswith('"'):
                end = rest.find('"', 1)
                if end < 0:
                    break
                token = rest[1:end]
                rest = rest[end + 1 :].lstrip()
            else:
                space = rest.find(" ")
                token = rest if space < 0 else rest[:space]
                rest = "" if space < 0 else rest[space + 1 :].lstrip()
            normalized = FinishTaskService._strip_git_ab_prefix(token)
            if normalized:
                paths.append(normalized)
        return paths

    @staticmethod
    def _parse_unified_diff_blocks(diff_text: str) -> list[dict[str, Any]]:
        normalized = str(diff_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            return []
        lines = normalized.split("\n")
        starts: list[tuple[int, list[str]]] = []
        for index, line in enumerate(lines):
            if line.startswith("diff --git "):
                paths = FinishTaskService._extract_paths_from_diff_git_header(line)
                starts.append((index, paths))
        if not starts:
            return [{"paths": [], "text": normalized.strip()}]
        blocks: list[dict[str, Any]] = []
        for idx, (start, paths) in enumerate(starts):
            end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
            block_text = "\n".join(lines[start:end]).strip()
            if not block_text:
                continue
            blocks.append({"paths": paths, "text": block_text})
        return blocks

    @staticmethod
    def _normalize_change_kind(value: Any, *, fallback: str = "modify") -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"add", "create", "created", "new"}:
            return "add"
        if normalized in {"delete", "deleted", "remove", "removed"}:
            return "delete"
        if normalized in {"modify", "modified", "update", "updated", "change", "changed"}:
            return "modify"
        return fallback

    @staticmethod
    def _change_type_to_kind(value: Any, *, fallback: str = "modify") -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"created", "create", "add"}:
            return "add"
        if normalized in {"deleted", "delete", "remove", "removed"}:
            return "delete"
        if normalized in {"updated", "update", "modify", "modified", "change", "changed"}:
            return "modify"
        return fallback

    @staticmethod
    def _change_kind_to_change_type(kind: str) -> str:
        if kind == "add":
            return "created"
        if kind == "delete":
            return "deleted"
        return "updated"

    @staticmethod
    def _extract_file_change_changes(item: dict[str, Any]) -> list[dict[str, Any]]:
        raw_changes = item.get("changes") if isinstance(item.get("changes"), list) else None
        rows = (
            raw_changes
            if raw_changes is not None
            else item.get("outputFiles")
            if isinstance(item.get("outputFiles"), list)
            else []
        )
        extracted: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path") or "").strip()
            if not path:
                continue
            if FinishTaskService._is_planningtree_path(path):
                continue
            kind = FinishTaskService._normalize_change_kind(
                raw.get("kind"),
                fallback=FinishTaskService._change_type_to_kind(raw.get("changeType"), fallback="modify"),
            )
            diff_value = raw.get("diff")
            if not isinstance(diff_value, str):
                diff_value = raw.get("patchText")
            diff_text = str(diff_value or "").strip() or None
            summary_value = raw.get("summary")
            summary = str(summary_value).strip() if isinstance(summary_value, str) and str(summary_value).strip() else None
            extracted.append(
                {
                    "path": path,
                    "kind": kind,
                    "diff": diff_text,
                    "summary": summary,
                }
            )
        return extracted

    @staticmethod
    def _output_files_from_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for change in changes:
            path = str(change.get("path") or "").strip()
            if not path:
                continue
            if FinishTaskService._is_planningtree_path(path):
                continue
            kind = FinishTaskService._normalize_change_kind(change.get("kind"), fallback="modify")
            file_entry: dict[str, Any] = {
                "path": path,
                "changeType": FinishTaskService._change_kind_to_change_type(kind),
                "summary": str(change.get("summary")).strip() if isinstance(change.get("summary"), str) and str(change.get("summary")).strip() else None,
                "kind": kind,
            }
            diff_text = str(change.get("diff") or "").strip()
            if diff_text:
                file_entry["diff"] = diff_text
            files.append(file_entry)
        return files

    @staticmethod
    def _score_paths_for_match(candidate_paths: list[str], target_path: str) -> int:
        if not target_path:
            return 0
        target_base = Path(target_path).name.lower()
        best = 0
        for candidate in candidate_paths:
            normalized = FinishTaskService._normalize_path_for_diff_match(candidate)
            if not normalized:
                continue
            if normalized == target_path:
                return 10000 + len(normalized)
            if target_path.endswith(f"/{normalized}") or normalized.endswith(f"/{target_path}"):
                best = max(best, 5000 + min(len(normalized), len(target_path)))
                continue
            if normalized.endswith(target_base) and target_base:
                best = max(best, 500 + len(normalized))
        return best

    @staticmethod
    def _resolve_diff_block_for_path(
        blocks: list[dict[str, Any]],
        *,
        path: str,
        file_index: int,
    ) -> dict[str, Any] | None:
        normalized_target = FinishTaskService._normalize_path_for_diff_match(path)
        best_index = -1
        best_score = 0
        for idx, block in enumerate(blocks):
            block_paths = block.get("paths")
            if not isinstance(block_paths, list):
                continue
            score = FinishTaskService._score_paths_for_match(block_paths, normalized_target)
            if score > best_score:
                best_score = score
                best_index = idx
        if best_index >= 0 and best_score >= 500:
            return blocks[best_index]
        if 0 <= file_index < len(blocks):
            return blocks[file_index]
        if len(blocks) == 1:
            return blocks[0]
        return None

    @staticmethod
    def _primary_path_from_block_paths(paths: list[str] | None) -> str:
        if not isinstance(paths, list):
            return ""
        for candidate in reversed(paths):
            normalized = FinishTaskService._normalize_path_for_diff_match(candidate)
            if normalized and normalized != "dev/null":
                return str(candidate)
        for candidate in reversed(paths):
            raw = str(candidate or "").strip()
            if raw:
                return raw
        return ""

    @staticmethod
    def _change_kind_from_diff_block_text(text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if (
            re.search(r"(?m)^new file mode\b", normalized)
            or re.search(r"(?m)^--- /dev/null$", normalized)
        ):
            return "add"
        if (
            re.search(r"(?m)^deleted file mode\b", normalized)
            or re.search(r"(?m)^\+\+\+ /dev/null$", normalized)
        ):
            return "delete"
        return "modify"

    @staticmethod
    def _changes_from_diff_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not blocks:
            return []
        changes: list[dict[str, Any]] = []
        seen = set()
        for block in blocks:
            block_paths = block.get("paths")
            path = FinishTaskService._primary_path_from_block_paths(
                block_paths if isinstance(block_paths, list) else None
            )
            normalized_path = FinishTaskService._normalize_path_for_diff_match(path)
            if (
                not normalized_path
                or normalized_path == "dev/null"
                or normalized_path in seen
                or FinishTaskService._is_planningtree_path(path)
            ):
                continue
            text = str(block.get("text") or "").strip()
            changes.append(
                {
                    "path": path,
                    "kind": FinishTaskService._change_kind_from_diff_block_text(text),
                    "diff": text or None,
                    "summary": "Hydrated from git diff",
                }
            )
            seen.add(normalized_path)
        return changes

    @staticmethod
    def _file_change_item_has_planningtree_paths(item: dict[str, Any]) -> bool:
        rows: list[Any] = []
        raw_changes = item.get("changes")
        raw_output_files = item.get("outputFiles")
        if isinstance(raw_changes, list):
            rows.extend(raw_changes)
        if isinstance(raw_output_files, list):
            rows.extend(raw_output_files)
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path") or "").strip()
            if FinishTaskService._is_planningtree_path(path):
                return True
        return False

    @staticmethod
    def _output_text_from_changes(changes: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            str(change.get("diff") or "").strip()
            for change in changes
            if str(change.get("diff") or "").strip()
        )

    @staticmethod
    def _should_trigger_live_file_change_hydrate(raw_event: dict[str, Any]) -> bool:
        method = str(raw_event.get("method") or "").strip()
        if method not in {"item/completed", "turn/completed"}:
            return False
        if method == "turn/completed":
            return True
        params = raw_event.get("params", {})
        item = params.get("item", {}) if isinstance(params, dict) else {}
        if not isinstance(item, dict):
            return False
        if str(item.get("kind") or "") != "tool":
            return False
        return True

    @classmethod
    def _normalize_worktree_diff_paths_for_git(
        cls,
        project_path: Path,
        paths: list[str],
    ) -> list[str]:
        normalized_paths: list[str] = []
        for raw_path in paths:
            candidate = str(raw_path or "").strip()
            if not candidate:
                continue
            path_obj = Path(candidate)
            if path_obj.is_absolute():
                try:
                    rel = path_obj.expanduser().resolve().relative_to(project_path)
                    candidate = rel.as_posix()
                except Exception:
                    pass
            candidate = candidate.replace("\\", "/")
            if cls._is_planningtree_path(candidate):
                continue
            normalized_paths.append(candidate)
        return normalized_paths

    def _get_worktree_diff_against_sha(
        self,
        *,
        project_path: Path,
        start_sha: str,
        paths: list[str] | None,
        project_id: str,
        node_id: str,
    ) -> str:
        if self._git_checkpoint_service is None:
            return ""
        normalized_paths = self._normalize_worktree_diff_paths_for_git(project_path, paths or [])
        try:
            if normalized_paths and hasattr(self._git_checkpoint_service, "get_worktree_diff_against_sha_for_paths"):
                return str(
                    self._git_checkpoint_service.get_worktree_diff_against_sha_for_paths(
                        project_path,
                        start_sha,
                        normalized_paths,
                    )
                    or ""
                )
            if hasattr(self._git_checkpoint_service, "get_worktree_diff_against_sha"):
                return str(
                    self._git_checkpoint_service.get_worktree_diff_against_sha(
                        project_path,
                        start_sha,
                    )
                    or ""
                )
        except Exception:
            logger.debug(
                "Failed to collect live worktree diff for %s/%s from %s",
                project_id,
                node_id,
                start_sha,
                exc_info=True,
            )
        return ""

    def _hydrate_execution_file_change_diff_from_worktree_v2(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        workspace_root: str | None,
        start_sha: str | None,
        hydrated_by: str = "finish_task_worktree_diff_v2",
        refresh_synthetic_from_full_diff: bool = False,
    ) -> None:
        runtime = self._thread_runtime_service_v2
        if (
            runtime is None
            or self._git_checkpoint_service is None
            or not isinstance(workspace_root, str)
            or not workspace_root.strip()
            or not isinstance(start_sha, str)
            or not start_sha.strip()
        ):
            return
        project_path = Path(workspace_root).expanduser().resolve()

        class _WorktreeRangeDiffSource(ExecutionFileChangeDiffSource):
            mode = "worktree_range"

            def __init__(
                self,
                *,
                owner: FinishTaskService,
                project_path: Path,
                start_sha: str,
                project_id: str,
                node_id: str,
            ) -> None:
                self._owner = owner
                self._project_path = project_path
                self._start_sha = start_sha
                self._project_id = project_id
                self._node_id = node_id

            def get_diff_for_paths(self, paths: list[str]) -> str:
                return self._owner._get_worktree_diff_against_sha(
                    project_path=self._project_path,
                    start_sha=self._start_sha,
                    paths=paths,
                    project_id=self._project_id,
                    node_id=self._node_id,
                )

            def get_full_diff(self) -> str:
                return self._owner._get_worktree_diff_against_sha(
                    project_path=self._project_path,
                    start_sha=self._start_sha,
                    paths=None,
                    project_id=self._project_id,
                    node_id=self._node_id,
                )

        diff_source = _WorktreeRangeDiffSource(
            owner=self,
            project_path=project_path,
            start_sha=start_sha,
            project_id=project_id,
            node_id=node_id,
        )
        hydrator = ExecutionFileChangeHydrator(logger=logger)
        query_service = runtime._query_service
        snapshot = query_service.get_thread_snapshot(
            project_id,
            node_id,
            "execution",
            publish_repairs=False,
            ensure_binding=False,
            allow_thread_read_hydration=False,
        )
        updated_snapshot, pending_events, _counters = hydrator.hydrate_turn_snapshot(
            snapshot=snapshot,
            turn_id=turn_id,
            diff_source=diff_source,
            hydrated_by=hydrated_by,
            project_id=project_id,
            node_id=node_id,
            refresh_synthetic_from_full_diff=refresh_synthetic_from_full_diff,
        )

        if pending_events:
            query_service.persist_thread_mutation(
                project_id,
                node_id,
                "execution",
                updated_snapshot,
                pending_events,
            )

    def _hydrate_execution_file_change_diff_v2(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        workspace_root: str | None,
        initial_sha: str | None,
        head_sha: str | None,
        refresh_synthetic_from_full_diff: bool = False,
    ) -> None:
        runtime = self._thread_runtime_service_v2
        if (
            runtime is None
            or self._git_checkpoint_service is None
            or not isinstance(workspace_root, str)
            or not workspace_root.strip()
            or not initial_sha
            or not head_sha
            or initial_sha == head_sha
        ):
            return

        project_path = Path(workspace_root)

        class _CommitRangeDiffSource(ExecutionFileChangeDiffSource):
            mode = "commit_range"

            def __init__(
                self,
                *,
                git_checkpoint_service: Any,
                project_path: Path,
                initial_sha: str,
                head_sha: str,
            ) -> None:
                self._git_checkpoint_service = git_checkpoint_service
                self._project_path = project_path
                self._initial_sha = initial_sha
                self._head_sha = head_sha

            def get_diff_for_paths(self, paths: list[str]) -> str:
                if not paths:
                    return ""
                if not hasattr(self._git_checkpoint_service, "get_diff_for_paths"):
                    return ""
                try:
                    return str(
                        self._git_checkpoint_service.get_diff_for_paths(
                            self._project_path,
                            self._initial_sha,
                            self._head_sha,
                            paths,
                        )
                        or ""
                    )
                except Exception:
                    logger.debug(
                        "Failed to hydrate execution diff text for %s/%s (paths=%s)",
                        project_id,
                        node_id,
                        paths,
                        exc_info=True,
                    )
                    return ""

            def get_full_diff(self) -> str:
                try:
                    return str(
                        self._git_checkpoint_service.get_diff(
                            self._project_path,
                            self._initial_sha,
                            self._head_sha,
                        )
                        or ""
                    )
                except Exception:
                    logger.debug(
                        "Failed to collect full execution diff for %s/%s turn %s",
                        project_id,
                        node_id,
                        turn_id,
                        exc_info=True,
                    )
                    return ""

        diff_source = _CommitRangeDiffSource(
            git_checkpoint_service=self._git_checkpoint_service,
            project_path=project_path,
            initial_sha=initial_sha,
            head_sha=head_sha,
        )
        hydrator = ExecutionFileChangeHydrator(logger=logger)
        query_service = runtime._query_service
        snapshot = query_service.get_thread_snapshot(
            project_id,
            node_id,
            "execution",
            publish_repairs=False,
            ensure_binding=False,
            allow_thread_read_hydration=False,
        )
        updated_snapshot, pending_events, _counters = hydrator.hydrate_turn_snapshot(
            snapshot=snapshot,
            turn_id=turn_id,
            diff_source=diff_source,
            hydrated_by="finish_task_diff_v2",
            project_id=project_id,
            node_id=node_id,
            refresh_synthetic_from_full_diff=refresh_synthetic_from_full_diff,
        )

        if pending_events:
            query_service.persist_thread_mutation(
                project_id,
                node_id,
                "execution",
                updated_snapshot,
                pending_events,
            )

    def fail_execution(
        self,
        project_id: str,
        node_id: str,
        error_message: str,
    ) -> None:
        """Persist execution as failed. Allows retry."""
        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None:
                return
            exec_state["status"] = "failed"
            exec_state["completed_at"] = iso_now()
            exec_state["error_message"] = error_message
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

    def _run_background_execution(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        thread_id: str,
        prompt: str,
        workspace_root: str | None,
        initial_sha: str = "",
        hierarchical_number: str = "",
        title: str = "",
    ) -> None:
        draft_lock = threading.Lock()
        accumulator = PartAccumulator()
        last_checkpoint_at = time.monotonic()

        def persist_activity_snapshot() -> None:
            self._persist_execution_message(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                content=accumulator.content_projection(),
                status="streaming",
                error=None,
                thread_id=thread_id,
                clear_active_turn=False,
                parts=accumulator.snapshot_parts(),
                items=accumulator.snapshot_items(),
            )

        def capture_delta(delta: str) -> None:
            nonlocal last_checkpoint_at
            checkpoint_content: str | None = None
            with draft_lock:
                accumulator.on_delta(delta)
                now = time.monotonic()
                if now - last_checkpoint_at >= _DRAFT_FLUSH_INTERVAL_SEC:
                    checkpoint_content = accumulator.content_projection()
                    last_checkpoint_at = now

            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_delta",
                    "message_id": assistant_message_id,
                    "delta": delta,
                    "item_id": "assistant_text",
                    "item_type": "assistant_text",
                    "phase": "delta",
                },
                thread_role="execution",
            )

            if checkpoint_content is not None:
                self._persist_execution_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=checkpoint_content,
                    status="streaming",
                    error=None,
                    thread_id=thread_id,
                    clear_active_turn=False,
                    parts=accumulator.snapshot_parts(),
                )

        def capture_tool_call(tool_name: str, arguments: dict[str, Any]) -> None:
            with draft_lock:
                item_id = accumulator.on_tool_call(tool_name, arguments)
                part_index = len(accumulator.parts) - 1
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_tool_call",
                    "message_id": assistant_message_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "part_index": part_index,
                    "item_id": item_id,
                    "item_type": "tool_call",
                    "phase": "started",
                },
                thread_role="execution",
            )

            with draft_lock:
                persist_activity_snapshot()

        def capture_item_event(phase: str, item: dict[str, Any]) -> None:
            with draft_lock:
                lifecycle_item_id = accumulator.on_item_event(phase, item)
            item_type = str(item.get("type") or "").strip()
            if item_type != "commandExecution":
                return

            call_id = str(item.get("id") or "").strip() or None
            tool_name = "shell_command"
            arguments = {
                "command": item.get("command"),
                "cwd": item.get("cwd"),
                "source": item.get("source"),
            }

            if phase == "started":
                with draft_lock:
                    tool_item_id = accumulator.on_tool_call(tool_name, arguments, call_id=call_id)
                    part_index = len(accumulator.parts) - 1
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_tool_call",
                        "message_id": assistant_message_id,
                        "tool_name": tool_name,
                        "arguments": arguments,
                        "call_id": call_id,
                        "part_index": part_index,
                        "item_id": tool_item_id,
                        "item_type": "tool_call",
                        "phase": "started",
                    },
                    thread_role="execution",
                )
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_item_lifecycle",
                        "message_id": assistant_message_id,
                        "item_id": lifecycle_item_id,
                        "item_type": item_type,
                        "phase": "started",
                        "payload": item,
                    },
                    thread_role="execution",
                )
                with draft_lock:
                    persist_activity_snapshot()
                return

            raw_status = str(item.get("status") or "").strip().lower()
            status = "error" if raw_status in {"failed", "incomplete", "error"} else "completed"
            output = item.get("aggregatedOutput")
            exit_code = item.get("exitCode")
            parsed_output = output if isinstance(output, str) and output else None
            parsed_exit_code = int(exit_code) if isinstance(exit_code, int) else None

            with draft_lock:
                tool_item_id = accumulator.on_tool_result(
                    call_id,
                    status=status,
                    output=parsed_output,
                    exit_code=parsed_exit_code,
                )
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_tool_result",
                    "message_id": assistant_message_id,
                    "call_id": call_id,
                    "status": status,
                    "output": parsed_output,
                    "exit_code": parsed_exit_code,
                    "item_id": tool_item_id,
                    "item_type": "tool_call",
                    "phase": "error" if status == "error" else "completed",
                },
                thread_role="execution",
            )
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_item_lifecycle",
                    "message_id": assistant_message_id,
                    "item_id": lifecycle_item_id,
                    "item_type": item_type,
                    "phase": "completed",
                    "payload": item,
                },
                thread_role="execution",
            )
            with draft_lock:
                persist_activity_snapshot()

        def capture_thread_status(payload: dict[str, Any]) -> None:
            with draft_lock:
                accumulator.on_thread_status(payload)
            status = payload.get("status", {})
            status_type = status.get("type", "unknown") if isinstance(status, dict) else "unknown"
            from backend.ai.part_accumulator import _status_label

            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_status",
                    "message_id": assistant_message_id,
                    "status_type": status_type,
                    "label": _status_label(status_type),
                    "item_id": "thread_status",
                    "item_type": "thread_status",
                    "phase": "delta",
                },
                thread_role="execution",
            )

            with draft_lock:
                persist_activity_snapshot()

        def capture_plan_delta(delta: str, item: dict[str, Any]) -> None:
            item_id = str(item.get("id") or "").strip()
            if not item_id or not isinstance(delta, str) or not delta:
                return

            with draft_lock:
                accumulator.on_plan_delta(delta, item)
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_plan_delta",
                    "message_id": assistant_message_id,
                    "item_id": item_id,
                    "delta": delta,
                    "item_type": "plan_item",
                    "phase": "delta",
                },
                thread_role="execution",
            )

            with draft_lock:
                persist_activity_snapshot()

        try:
            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=self._chat_timeout,
                cwd=workspace_root,
                writable_roots=[workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None,
                on_delta=capture_delta,
                on_tool_call=capture_tool_call,
                on_plan_delta=capture_plan_delta,
                on_thread_status=capture_thread_status,
                on_item_event=capture_item_event,
            )

            with draft_lock:
                final_plan_item = result.get("final_plan_item")
                if isinstance(final_plan_item, dict):
                    text = str(final_plan_item.get("text") or "")
                    item_id = str(final_plan_item.get("id") or "")
                    if text.strip() and item_id.strip():
                        existing_plan_item = next(
                            (
                                part
                                for part in accumulator.parts
                                if part.get("type") == "plan_item" and part.get("item_id") == item_id
                            ),
                            None,
                        )
                        if existing_plan_item is None:
                            accumulator.on_plan_delta(text, final_plan_item)
                accumulator.finalize(keep_status_blocks=True)
                final_parts = accumulator.snapshot_parts()
                final_items = accumulator.snapshot_items()
                streamed_content = accumulator.content_projection()
            stdout = str(result.get("stdout", "") or "")
            final_content = stdout or streamed_content

            # 1. CRITICAL: git commit. Failure → fail_execution()
            head_sha: str | None = None
            commit_msg: str | None = None
            changed: list[dict[str, Any]] = []
            if self._git_checkpoint_service is not None and workspace_root:
                commit_msg = self._git_checkpoint_service.build_commit_message(
                    hierarchical_number, title
                )
                new_sha = self._git_checkpoint_service.commit_if_changed(
                    Path(workspace_root), commit_msg
                )
                head_sha = new_sha if new_sha else initial_sha

                # 2. BEST-EFFORT: changed files metadata
                if new_sha:
                    try:
                        from backend.errors.app_errors import GitCheckpointError
                        changed = self._git_checkpoint_service.get_changed_files(
                            Path(workspace_root), initial_sha, head_sha
                        )
                    except Exception:
                        logger.warning(
                            "Failed to collect changed files for %s/%s",
                            project_id, node_id,
                        )
                        changed = []
                else:
                    commit_msg = None  # No diff → no commit message
            else:
                from backend.services.workspace_sha import compute_workspace_sha
                head_sha = compute_workspace_sha(Path(workspace_root)) if workspace_root else None

            # 3. CRITICAL: execution state → completed
            self.complete_execution(
                project_id, node_id,
                head_sha=head_sha,
                commit_message=commit_msg,
                changed_files=changed,
            )

            # === POINT OF NO RETURN: execution state is "completed" ===
            # Errors below are best-effort only — do NOT call fail_execution()

            # 4. BEST-EFFORT: finalize execution chat message first (clears active_turn_id)
            try:
                persisted = self._persist_execution_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=final_content,
                    status="completed",
                    error=None,
                    thread_id=thread_id,
                    clear_active_turn=True,
                    parts=final_parts,
                    items=final_items,
                )
                if persisted:
                    self._chat_event_broker.publish(
                        project_id,
                        node_id,
                        {
                            "type": "assistant_completed",
                            "message_id": assistant_message_id,
                            "content": final_content,
                            "thread_id": thread_id,
                        },
                        thread_role="execution",
                    )
            except Exception:
                logger.warning("Failed to persist/publish completed message for %s/%s", project_id, node_id)

            # 5. BEST-EFFORT: start automated local review (after execution session is finalized)
            try:
                self._start_auto_review(
                    project_id=project_id,
                    node_id=node_id,
                    workspace_root=workspace_root,
                )
            except Exception:
                logger.warning(
                    "Failed to start auto-review for %s/%s",
                    project_id,
                    node_id,
                    exc_info=True,
                )
        except Exception as exc:
            logger.debug(
                "Execution turn failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )
            try:
                with draft_lock:
                    accumulator.finalize()
                    error_parts = accumulator.snapshot_parts()
                    streamed_content = accumulator.content_projection()
                persisted = self._persist_execution_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=streamed_content,
                    status="error",
                    error=str(exc),
                    thread_id=thread_id,
                    clear_active_turn=True,
                    parts=error_parts,
                    items=accumulator.snapshot_items(),
                )
            except Exception:
                persisted = False
                logger.debug("Failed to persist execution error state", exc_info=True)

            if persisted:
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_error",
                        "message_id": assistant_message_id,
                        "error": str(exc),
                    },
                    thread_role="execution",
                )

            try:
                self.fail_execution(project_id, node_id, error_message=str(exc))
            except Exception:
                logger.debug("Failed to persist failed execution state", exc_info=True)
        finally:
            self._clear_live_job(project_id, node_id, turn_id)

    def _run_background_execution_v2(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        thread_id: str,
        prompt: str,
        workspace_root: str | None,
        initial_sha: str = "",
        hierarchical_number: str = "",
        title: str = "",
        enable_auto_review: bool,
    ) -> None:
        if self._thread_runtime_service_v2 is None:
            logger.warning(
                "Skipping V2 execution for %s/%s: runtime unavailable.",
                project_id,
                node_id,
            )
            self._clear_live_job(project_id, node_id, turn_id)
            return

        turn_finalized = False
        try:
            last_live_file_change_hydrate_at = 0.0

            def handle_live_file_change_hydration(raw_event: dict[str, Any]) -> None:
                nonlocal last_live_file_change_hydrate_at
                if not self._should_trigger_live_file_change_hydrate(raw_event):
                    return
                method = str(raw_event.get("method") or "").strip()
                now_mono = time.monotonic()
                if (
                    method != "turn/completed"
                    and now_mono - last_live_file_change_hydrate_at < _LIVE_FILE_CHANGE_HYDRATE_DEBOUNCE_SEC
                ):
                    return
                last_live_file_change_hydrate_at = now_mono
                self._hydrate_execution_file_change_diff_from_worktree_v2(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    workspace_root=workspace_root,
                    start_sha=initial_sha,
                    hydrated_by="finish_task_worktree_live",
                    refresh_synthetic_from_full_diff=True,
                )

            stream_result = self._thread_runtime_service_v2.stream_agent_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                thread_id=thread_id,
                turn_id=turn_id,
                prompt=prompt,
                cwd=workspace_root,
                writable_roots=[workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None,
                timeout_sec=self._chat_timeout,
                on_raw_event_applied=handle_live_file_change_hydration,
            )
            result = stream_result["result"]
            turn_status = str(stream_result.get("turnStatus") or "").strip().lower()
            outcome = self._thread_runtime_service_v2.outcome_from_turn_status(turn_status)
            if outcome != "completed":
                error_message = f"Execution rehearsal returned terminal status '{turn_status or 'unknown'}'."
                error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role="execution",
                    turn_id=turn_id,
                    thread_id=thread_id,
                    message=error_message,
                )
                self._thread_runtime_service_v2.complete_turn(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role="execution",
                    turn_id=turn_id,
                    outcome="failed",
                    error_item=error_item,
                )
                turn_finalized = True
                raise FinishTaskNotAllowed(error_message)

            head_sha: str | None = None
            commit_msg: str | None = None
            changed: list[dict[str, Any]] = []
            if self._git_checkpoint_service is not None and workspace_root:
                commit_msg = self._git_checkpoint_service.build_commit_message(
                    hierarchical_number, title
                )
                new_sha = self._git_checkpoint_service.commit_if_changed(
                    Path(workspace_root), commit_msg
                )
                head_sha = new_sha if new_sha else initial_sha
                if new_sha:
                    try:
                        changed = self._git_checkpoint_service.get_changed_files(
                            Path(workspace_root), initial_sha, head_sha
                        )
                    except Exception:
                        logger.warning(
                            "Failed to collect changed files for %s/%s",
                            project_id,
                            node_id,
                        )
                        changed = []
                else:
                    commit_msg = None
            else:
                from backend.services.workspace_sha import compute_workspace_sha

                head_sha = compute_workspace_sha(Path(workspace_root)) if workspace_root else None

            self.complete_execution(
                project_id,
                node_id,
                head_sha=head_sha,
                commit_message=commit_msg,
                changed_files=changed,
                publish_legacy_event=False,
            )
            self._hydrate_execution_file_change_diff_v2(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                workspace_root=workspace_root,
                initial_sha=initial_sha,
                head_sha=head_sha,
                refresh_synthetic_from_full_diff=True,
            )
            self._thread_runtime_service_v2.complete_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="execution",
                turn_id=turn_id,
                outcome="completed",
            )
            turn_finalized = True

            self._publish_workflow_refresh(
                project_id=project_id,
                node_id=node_id,
                reason="execution_completed",
            )

            if enable_auto_review:
                try:
                    self._start_auto_review_v2(
                        project_id=project_id,
                        node_id=node_id,
                        workspace_root=workspace_root,
                    )
                except Exception:
                    logger.debug(
                        "Failed to start V2 auto-review after execution for %s/%s",
                        project_id,
                        node_id,
                        exc_info=True,
                    )
            elif self._review_service is not None:
                try:
                    self._review_service.start_local_review(project_id, node_id)
                except Exception:
                    logger.debug(
                        "Failed to auto-open local review after rehearsal execution for %s/%s",
                        project_id,
                        node_id,
                        exc_info=True,
                    )
        except Exception as exc:
            logger.debug(
                "V2 execution failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )
            if not turn_finalized:
                try:
                    error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="execution",
                        turn_id=turn_id,
                        thread_id=thread_id,
                        message=str(exc),
                    )
                    self._thread_runtime_service_v2.complete_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="execution",
                        turn_id=turn_id,
                        outcome="failed",
                        error_item=error_item,
                    )
                    turn_finalized = True
                except Exception:
                    logger.debug(
                        "Failed to finalize V2 execution turn for %s/%s",
                        project_id,
                        node_id,
                        exc_info=True,
                    )

            try:
                self.fail_execution(project_id, node_id, error_message=str(exc))
            except Exception:
                logger.debug("Failed to persist failed V2 execution state", exc_info=True)
            self._publish_workflow_refresh(
                project_id=project_id,
                node_id=node_id,
                reason="execution_failed",
            )
        finally:
            self._clear_live_job(project_id, node_id, turn_id)

    def _validate_finish_task_locked(
        self,
        project_id: str,
        node_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_dir: Path,
    ) -> str:
        if node.get("node_kind") == "review":
            raise FinishTaskNotAllowed("Finish Task is only available for task nodes.")

        spec_meta = _load_spec_meta_from_node_dir(node_dir)
        if not spec_meta.get("confirmed_at"):
            raise FinishTaskNotAllowed("Spec must be confirmed before Finish Task.")

        child_ids = node.get("child_ids") or []
        if len(child_ids) > 0:
            raise FinishTaskNotAllowed("Finish Task is only available for leaf nodes (no children).")

        node_status = node.get("status", "")
        if node_status not in ("ready", "in_progress"):
            raise FinishTaskNotAllowed(
                f"Node status must be 'ready' or 'in_progress', got '{node_status}'."
            )

        exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
        if exec_state is not None:
            status = exec_state.get("status")
            if status == "executing":
                raise FinishTaskNotAllowed("Execution is already in progress for this node.")
            if status == "failed":
                pass  # Allow retry from failed
            elif status is not None and status != "idle":
                raise FinishTaskNotAllowed("Execution has already been started for this node.")

        spec_path = node_dir / planningtree_workspace.SPEC_FILE_NAME
        spec_content = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
        if not spec_content.strip():
            raise FinishTaskNotAllowed("Spec must be non-empty before Finish Task.")

        # Git guardrails
        if self._git_checkpoint_service is not None:
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            if workspace_root:
                expected_head = self._resolve_expected_baseline_sha(project_id, node_id, snapshot)
                blockers = self._git_checkpoint_service.validate_guardrails(
                    Path(workspace_root), expected_head=expected_head
                )
                if blockers:
                    raise FinishTaskNotAllowed(blockers[0])

        return spec_content

    def _ensure_execution_thread(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> dict[str, Any]:
        writable_roots = [workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None
        try:
            return self._thread_lineage_service.ensure_forked_thread(
                project_id,
                node_id,
                "execution",
                source_node_id=node_id,
                source_role="audit",
                fork_reason="execution_bootstrap",
                workspace_root=workspace_root,
                base_instructions=build_execution_base_instructions(),
                dynamic_tools=[],
                writable_roots=writable_roots,
            )
        except Exception as exc:
            raise FinishTaskNotAllowed(f"Execution backend unavailable: {exc}") from exc

    def _ensure_execution_thread_id_v2(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> str:
        if self._thread_lineage_service is None:
            raise FinishTaskNotAllowed("Execution lineage service unavailable for V2 runtime.")
        writable_roots = [workspace_root] if isinstance(workspace_root, str) and workspace_root.strip() else None
        try:
            entry = self._thread_lineage_service.ensure_thread_binding_v2(
                project_id,
                node_id,
                "execution",
                workspace_root,
                base_instructions=build_execution_base_instructions(),
                dynamic_tools=[],
                writable_roots=writable_roots,
            )
        except Exception as exc:
            raise FinishTaskNotAllowed(f"Execution backend unavailable: {exc}") from exc
        thread_id = str(entry.get("threadId") or "").strip()
        if not thread_id:
            raise FinishTaskNotAllowed("Execution bootstrap did not return a V2 thread id.")
        return thread_id

    def _persist_execution_message(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        content: str,
        status: str,
        error: str | None,
        thread_id: str | None,
        clear_active_turn: bool,
        parts: list[dict[str, Any]] | None = None,
        items: list[dict[str, Any]] | None = None,
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id,
                node_id,
                thread_role="execution",
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False

            message = None
            for candidate in reversed(session.get("messages", [])):
                if candidate.get("message_id") == assistant_message_id:
                    message = candidate
                    break
            if message is None:
                return False

            message["content"] = content
            message["status"] = status
            message["error"] = error
            message["updated_at"] = iso_now()
            if parts is not None:
                message["parts"] = parts
            if items is not None:
                message["items"] = items

            if thread_id is not None:
                session["thread_id"] = thread_id
            if clear_active_turn:
                session["active_turn_id"] = None

            self._storage.chat_state_store.write_session(
                project_id,
                node_id,
                session,
                thread_role="execution",
            )
            return True

    def _resolve_expected_baseline_sha(
        self,
        project_id: str,
        node_id: str,
        snapshot: dict[str, Any],
    ) -> str | None:
        """Resolve the expected git HEAD from the checkpoint chain.

        Returns a git commit SHA (40-char hex) for guardrail check 7,
        or None if no baseline can be determined (root node, split before git init).
        """
        node_index = snapshot.get("tree_state", {}).get("node_index", {})
        node = node_index.get(node_id, {})
        parent_id = node.get("parent_id")

        if not parent_id:
            return None

        parent = node_index.get(parent_id, {})
        review_node_id = parent.get("review_node_id")
        if not review_node_id:
            return None

        review_state = self._storage.review_state_store.read_state(project_id, review_node_id)
        if not review_state:
            return None

        checkpoints = review_state.get("checkpoints", [])
        if not checkpoints:
            return None

        latest_sha = checkpoints[-1].get("sha", "")
        if self._git_checkpoint_service is not None:
            if self._git_checkpoint_service.is_git_commit_sha(latest_sha):
                return latest_sha
            # K0 uses sha256: format — fall back to k0_git_head_sha
            k0_git_head = review_state.get("k0_git_head_sha")
            if self._git_checkpoint_service.is_git_commit_sha(k0_git_head):
                return k0_git_head

        return None

    def _compute_initial_sha(
        self,
        project_id: str,
        node_id: str,
        snapshot: dict[str, Any],
    ) -> str:
        """Capture initial SHA for execution. Uses git if available, falls back to workspace SHA."""
        if self._git_checkpoint_service is not None:
            workspace_root = self._workspace_root_from_snapshot(snapshot)
            if workspace_root:
                return self._git_checkpoint_service.capture_head_sha(Path(workspace_root))

        workspace_root = self._workspace_root_from_snapshot(snapshot)
        if workspace_root is None:
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        from backend.services.workspace_sha import compute_workspace_sha
        return compute_workspace_sha(Path(workspace_root))

    def _load_confirmed_frame_content(self, node_dir: Path) -> str:
        meta_path = node_dir / "frame.meta.json"
        frame_meta = load_json(meta_path, default=None)
        if not isinstance(frame_meta, dict):
            frame_meta = dict(_DEFAULT_FRAME_META)
        frame_content = str(frame_meta.get("confirmed_content") or "")
        if frame_content:
            return frame_content
        frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
        if frame_path.exists():
            return frame_path.read_text(encoding="utf-8")
        return ""

    def _resolve_node_dir(self, snapshot: dict[str, Any], node_id: str) -> Path:
        project = snapshot.get("project", {})
        raw_path = str(project.get("project_path") or "").strip()
        if not raw_path:
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        project_path = Path(raw_path)
        node_dir = planningtree_workspace.resolve_node_dir(project_path, snapshot, node_id)
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

    def _assert_rehearsal_workspace_allowed(self, workspace_root: str | None) -> Path:
        raw_workspace_root = str(workspace_root or "").strip()
        if not raw_workspace_root:
            raise ExecutionAuditRehearsalWorkspaceUnsafe(
                "Execution/audit V2 rehearsal requires a project workspace root."
            )
        if self._rehearsal_workspace_root is None:
            raise ExecutionAuditRehearsalWorkspaceUnsafe(
                "Execution/audit V2 rehearsal requires PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT to be configured."
            )
        resolved_workspace_root = Path(raw_workspace_root).expanduser().resolve()
        try:
            resolved_workspace_root.relative_to(self._rehearsal_workspace_root)
        except ValueError as exc:
            raise ExecutionAuditRehearsalWorkspaceUnsafe(
                "Execution/audit V2 rehearsal is allowed only for workspaces under the configured rehearsal root."
            ) from exc
        return resolved_workspace_root

    def _publish_workflow_refresh(self, *, project_id: str, node_id: str, reason: str) -> None:
        if self._workflow_event_publisher_v2 is None:
            return
        exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
        execution_status = (str(exec_state.get("status") or "").strip() or None) if exec_state else None
        self._workflow_event_publisher_v2.publish_workflow_updated(
            project_id=project_id,
            node_id=node_id,
            execution_state=execution_status,
            review_state=None,
        )
        self._workflow_event_publisher_v2.publish_detail_invalidate(
            project_id=project_id,
            node_id=node_id,
            reason=reason,
        )

    def _job_key(self, project_id: str, node_id: str) -> str:
        return f"{project_id}::{node_id}"

    def _mark_live_job(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_jobs_lock:
            self._live_jobs[self._job_key(project_id, node_id)] = turn_id
        if self._chat_service is not None:
            self._chat_service.register_external_live_turn(
                project_id,
                node_id,
                "execution",
                turn_id,
            )

    def _clear_live_job(self, project_id: str, node_id: str, turn_id: str) -> None:
        with self._live_jobs_lock:
            key = self._job_key(project_id, node_id)
            if self._live_jobs.get(key) == turn_id:
                self._live_jobs.pop(key, None)
        if self._chat_service is not None:
            self._chat_service.clear_external_live_turn(
                project_id,
                node_id,
                "execution",
                turn_id,
            )

    def _ensure_audit_thread(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> str:
        if self._thread_lineage_service is None:
            raise FinishTaskNotAllowed("Thread lineage service unavailable for audit runtime.")
        session = self._thread_lineage_service.resume_or_rebuild_session(
            project_id,
            node_id,
            "audit",
            workspace_root,
            base_instructions=build_auto_review_base_instructions(),
        )
        thread_id = str(session.get("thread_id") or "").strip()
        if not thread_id:
            raise FinishTaskNotAllowed("Audit thread bootstrap did not return a thread id.")
        return thread_id

    def _ensure_audit_thread_id_v2(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> str:
        if self._thread_lineage_service is None:
            raise FinishTaskNotAllowed("Thread lineage service unavailable for audit V2 runtime.")
        try:
            entry = self._thread_lineage_service.ensure_thread_binding_v2(
                project_id,
                node_id,
                "audit",
                workspace_root,
                base_instructions=build_auto_review_base_instructions(),
                dynamic_tools=None,
                writable_roots=None,
            )
        except Exception as exc:
            raise FinishTaskNotAllowed(f"Audit backend unavailable: {exc}") from exc
        thread_id = str(entry.get("threadId") or "").strip()
        if not thread_id:
            raise FinishTaskNotAllowed("Audit thread bootstrap did not return a V2 thread id.")
        return thread_id

    # -- Automated Local Review --------------------------------------

    def _start_auto_review_v2(
        self,
        *,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> bool:
        if self._thread_runtime_service_v2 is None:
            raise FinishTaskNotAllowed("Auto-review V2 runtime is unavailable.")

        turn_id = new_id("auto_review")
        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None or exec_state.get("status") != "completed":
                logger.debug(
                    "Skipping V2 auto-review for %s/%s: execution status is not 'completed'.",
                    project_id,
                    node_id,
                )
                return False

            existing_auto_review = exec_state.get("auto_review")
            if isinstance(existing_auto_review, dict) and existing_auto_review.get("status") in (
                "running",
                "completed",
            ):
                logger.debug(
                    "Skipping V2 auto-review for %s/%s: already %s.",
                    project_id,
                    node_id,
                    existing_auto_review.get("status"),
                )
                return False

        thread_id = self._ensure_audit_thread_id_v2(project_id, node_id, workspace_root)
        try:
            self._thread_runtime_service_v2.begin_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="audit",
                origin="auto_review",
                created_items=[],
                turn_id=turn_id,
            )
        except ChatTurnAlreadyActive:
            logger.warning(
                "Skipping V2 auto-review for %s/%s: audit thread already has an active turn.",
                project_id,
                node_id,
            )
            return False

        now = iso_now()
        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is not None:
                exec_state["auto_review"] = {
                    "status": "running",
                    "started_at": now,
                    "completed_at": None,
                    "summary": None,
                    "checkpoint_summary": None,
                    "overall_severity": None,
                    "overall_score": None,
                    "findings": [],
                    "error_message": None,
                }
                self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

        self._publish_workflow_refresh(
            project_id=project_id,
            node_id=node_id,
            reason="auto_review_started",
        )

        threading.Thread(
            target=self._run_background_auto_review_v2,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "thread_id": thread_id,
                "workspace_root": workspace_root,
            },
            daemon=True,
        ).start()
        return True

    def _run_background_auto_review_v2(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        thread_id: str,
        workspace_root: str | None,
    ) -> None:
        if self._thread_runtime_service_v2 is None:
            logger.warning(
                "Skipping V2 auto-review for %s/%s: runtime unavailable.",
                project_id,
                node_id,
            )
            return

        turn_finalized = False
        try:
            prompt = build_auto_review_prompt(
                self._storage,
                project_id,
                node_id,
                workspace_root,
                self._git_checkpoint_service,
            )
            stream_result = self._thread_runtime_service_v2.stream_agent_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="audit",
                thread_id=thread_id,
                turn_id=turn_id,
                prompt=prompt,
                cwd=workspace_root,
                writable_roots=None,
                sandbox_profile="read_only",
                output_schema=build_auto_review_output_schema(),
                timeout_sec=self._chat_timeout,
            )
            result = stream_result["result"]
            turn_status = str(stream_result.get("turnStatus") or "").strip().lower()
            outcome = self._thread_runtime_service_v2.outcome_from_turn_status(turn_status)
            if outcome != "completed":
                error_message = f"Auto-review returned terminal status '{turn_status or 'unknown'}'."
                error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role="audit",
                    turn_id=turn_id,
                    thread_id=thread_id,
                    message=error_message,
                )
                self._thread_runtime_service_v2.complete_turn(
                    project_id=project_id,
                    node_id=node_id,
                    thread_role="audit",
                    turn_id=turn_id,
                    outcome="failed",
                    error_item=error_item,
                )
                turn_finalized = True
                raise FinishTaskNotAllowed(error_message)

            stdout = str(result.get("stdout", "") or "")
            review_result = extract_auto_review_result(stdout)
            if not review_result:
                raise FinishTaskNotAllowed("Auto-review did not return a valid structured result.")

            now = iso_now()
            with self._storage.project_lock(project_id):
                exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
                if exec_state is not None:
                    current_auto_review = exec_state.get("auto_review")
                    started_at = (
                        current_auto_review.get("started_at")
                        if isinstance(current_auto_review, dict)
                        else None
                    )
                    exec_state["auto_review"] = {
                        "status": "completed",
                        "started_at": started_at,
                        "completed_at": now,
                        "summary": review_result["summary"],
                        "checkpoint_summary": review_result["checkpoint_summary"],
                        "overall_severity": review_result["overall_severity"],
                        "overall_score": review_result["overall_score"],
                        "findings": review_result["findings"],
                        "error_message": None,
                    }
                    self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            self._thread_runtime_service_v2.complete_turn(
                project_id=project_id,
                node_id=node_id,
                thread_role="audit",
                turn_id=turn_id,
                outcome="completed",
            )
            turn_finalized = True
            self._publish_workflow_refresh(
                project_id=project_id,
                node_id=node_id,
                reason="auto_review_completed",
            )
            self._auto_accept_local_review(project_id=project_id, node_id=node_id)
        except Exception as exc:
            logger.debug(
                "V2 auto-review failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )
            now = iso_now()
            with self._storage.project_lock(project_id):
                exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
                if exec_state is not None:
                    current = exec_state.get("auto_review")
                    exec_state["auto_review"] = {
                        "status": "failed",
                        "started_at": current.get("started_at") if isinstance(current, dict) else None,
                        "completed_at": now,
                        "summary": current.get("summary") if isinstance(current, dict) else None,
                        "checkpoint_summary": current.get("checkpoint_summary") if isinstance(current, dict) else None,
                        "overall_severity": current.get("overall_severity") if isinstance(current, dict) else None,
                        "overall_score": current.get("overall_score") if isinstance(current, dict) else None,
                        "findings": current.get("findings", []) if isinstance(current, dict) else [],
                        "error_message": str(exc),
                    }
                    self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            if not turn_finalized:
                try:
                    error_item = self._thread_runtime_service_v2.build_error_item_for_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="audit",
                        turn_id=turn_id,
                        thread_id=thread_id,
                        message=str(exc),
                    )
                    self._thread_runtime_service_v2.complete_turn(
                        project_id=project_id,
                        node_id=node_id,
                        thread_role="audit",
                        turn_id=turn_id,
                        outcome="failed",
                        error_item=error_item,
                    )
                    turn_finalized = True
                except Exception:
                    logger.debug(
                        "Failed to finalize V2 auto-review turn for %s/%s",
                        project_id,
                        node_id,
                        exc_info=True,
                    )
            self._publish_workflow_refresh(
                project_id=project_id,
                node_id=node_id,
                reason="auto_review_failed",
            )

    def _start_auto_review(
        self,
        *,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> bool:
        if self._codex_client is None or self._chat_event_broker is None:
            logger.debug(
                "Skipping auto-review for %s/%s: dependencies unavailable.",
                project_id,
                node_id,
            )
            return False

        turn_id = new_id("auto_review")
        assistant_message_id = new_id("msg")
        now = iso_now()
        assistant_message = {
            "message_id": assistant_message_id,
            "role": "assistant",
            "content": "",
            "status": "pending",
            "error": None,
            "turn_id": turn_id,
            "created_at": now,
            "updated_at": now,
        }

        with self._storage.project_lock(project_id):
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None or exec_state.get("status") != "completed":
                logger.debug(
                    "Skipping auto-review for %s/%s: execution status is not 'completed'.",
                    project_id,
                    node_id,
                )
                return False

            existing_auto_review = exec_state.get("auto_review")
            if isinstance(existing_auto_review, dict) and existing_auto_review.get("status") in (
                "running",
                "completed",
            ):
                logger.debug(
                    "Skipping auto-review for %s/%s: already %s.",
                    project_id,
                    node_id,
                    existing_auto_review.get("status"),
                )
                return False

            session = self._storage.chat_state_store.read_session(
                project_id, node_id, thread_role="audit"
            )
            if session.get("active_turn_id"):
                logger.warning(
                    "Skipping auto-review for %s/%s: audit session already has active turn %s.",
                    project_id,
                    node_id,
                    session.get("active_turn_id"),
                )
                return False

            session["active_turn_id"] = turn_id
            session["messages"].append(assistant_message)
            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role="audit"
            )

            exec_state["auto_review"] = {
                "status": "running",
                "started_at": now,
                "completed_at": None,
                "summary": None,
                "checkpoint_summary": None,
                "overall_severity": None,
                "overall_score": None,
                "findings": [],
                "error_message": None,
                "review_message_id": assistant_message_id,
            }
            self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

        if self._chat_service is not None:
            self._chat_service.register_external_live_turn(
                project_id, node_id, "audit", turn_id
            )

        self._chat_event_broker.publish(
            project_id,
            node_id,
            {
                "type": "message_created",
                "assistant_message": assistant_message,
                "active_turn_id": turn_id,
            },
            thread_role="audit",
        )
        self._chat_event_broker.publish(
            project_id,
            node_id,
            {"type": "auto_review_started", "node_id": node_id, "turn_id": turn_id, "message_id": assistant_message_id},
            thread_role="audit",
        )

        threading.Thread(
            target=self._run_background_auto_review,
            kwargs={
                "project_id": project_id,
                "node_id": node_id,
                "turn_id": turn_id,
                "assistant_message_id": assistant_message_id,
                "workspace_root": workspace_root,
            },
            daemon=True,
        ).start()
        return True

    def _run_background_auto_review(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        workspace_root: str | None,
    ) -> None:
        thread_id: str | None = None
        draft_lock = threading.Lock()
        accumulator = PartAccumulator()
        last_checkpoint_at = time.monotonic()

        def capture_delta(delta: str) -> None:
            nonlocal last_checkpoint_at
            checkpoint_content: str | None = None
            with draft_lock:
                accumulator.on_delta(delta)
                now_t = time.monotonic()
                if now_t - last_checkpoint_at >= _DRAFT_FLUSH_INTERVAL_SEC:
                    checkpoint_content = accumulator.content_projection()
                    last_checkpoint_at = now_t

            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_delta",
                    "message_id": assistant_message_id,
                    "delta": delta,
                    "item_id": "assistant_text",
                    "item_type": "assistant_text",
                    "phase": "delta",
                },
                thread_role="audit",
            )

            if checkpoint_content is not None:
                self._persist_auto_review_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=checkpoint_content,
                    status="streaming",
                    error=None,
                    thread_id=thread_id,
                    clear_active_turn=False,
                    parts=accumulator.snapshot_parts(),
                    items=accumulator.snapshot_items(),
                )

        def capture_tool_call(tool_name: str, arguments: dict[str, Any]) -> None:
            with draft_lock:
                item_id = accumulator.on_tool_call(tool_name, arguments)
                part_index = len(accumulator.parts) - 1
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_tool_call",
                    "message_id": assistant_message_id,
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "part_index": part_index,
                    "item_id": item_id,
                    "item_type": "tool_call",
                    "phase": "started",
                },
                thread_role="audit",
            )

        def capture_thread_status(payload: dict[str, Any]) -> None:
            with draft_lock:
                accumulator.on_thread_status(payload)
            status = payload.get("status", {})
            status_type = status.get("type", "unknown") if isinstance(status, dict) else "unknown"
            from backend.ai.part_accumulator import _status_label

            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "assistant_status",
                    "message_id": assistant_message_id,
                    "status_type": status_type,
                    "label": _status_label(status_type),
                    "item_id": "thread_status",
                    "item_type": "thread_status",
                    "phase": "delta",
                },
                thread_role="audit",
            )

        try:
            if self._thread_lineage_service is None:
                raise FinishTaskNotAllowed("Thread lineage service unavailable for auto-review.")

            session = self._thread_lineage_service.resume_or_rebuild_session(
                project_id,
                node_id,
                "audit",
                workspace_root,
                base_instructions=build_auto_review_base_instructions(),
            )
            thread_id = str(session.get("thread_id") or "").strip()
            if not thread_id:
                raise FinishTaskNotAllowed("Auto-review audit thread did not return a thread id.")

            self._persist_auto_review_thread_id(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                thread_id=thread_id,
            )

            prompt = build_auto_review_prompt(
                self._storage,
                project_id,
                node_id,
                workspace_root,
                self._git_checkpoint_service,
            )

            result = self._codex_client.run_turn_streaming(
                prompt,
                thread_id=thread_id,
                timeout_sec=self._chat_timeout,
                cwd=workspace_root,
                writable_roots=None,
                sandbox_profile="read_only",
                on_delta=capture_delta,
                on_tool_call=capture_tool_call,
                on_thread_status=capture_thread_status,
                output_schema=build_auto_review_output_schema(),
            )

            with draft_lock:
                accumulator.finalize()
                streamed_content = accumulator.content_projection()
                final_parts = accumulator.snapshot_parts()
                final_items = accumulator.snapshot_items()

            stdout = str(result.get("stdout", "") or "")
            review_result = extract_auto_review_result(stdout) or extract_auto_review_result(
                streamed_content
            )
            if not review_result:
                raise FinishTaskNotAllowed(
                    "Auto-review did not return a valid structured result."
                )

            now = iso_now()
            with self._storage.project_lock(project_id):
                exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
                if exec_state is not None:
                    auto_review = exec_state.get("auto_review") or {}
                    auto_review.update({
                        "status": "completed",
                        "completed_at": now,
                        "summary": review_result["summary"],
                        "checkpoint_summary": review_result["checkpoint_summary"],
                        "overall_severity": review_result["overall_severity"],
                        "overall_score": review_result["overall_score"],
                        "findings": review_result["findings"],
                        "error_message": None,
                    })
                    exec_state["auto_review"] = auto_review
                    self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

            severity = review_result["overall_severity"]
            score = review_result["overall_score"]
            final_content = (
                f"## Automated Local Review\n\n"
                f"**Severity:** {severity} | **Score:** {score}/100\n\n"
                f"{review_result['summary']}"
            )

            finalized_parts = [dict(p) for p in final_parts if p.get("type") != "assistant_text"]
            finalized_parts.append({"type": "assistant_text", "content": final_content, "is_streaming": False})

            persisted = self._persist_auto_review_message(
                project_id=project_id,
                node_id=node_id,
                turn_id=turn_id,
                assistant_message_id=assistant_message_id,
                content=final_content,
                status="completed",
                error=None,
                thread_id=str(result.get("thread_id") or thread_id or ""),
                clear_active_turn=True,
                parts=finalized_parts,
                items=final_items,
            )

            if persisted:
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "assistant_completed",
                        "message_id": assistant_message_id,
                        "content": final_content,
                        "thread_id": str(result.get("thread_id") or thread_id or ""),
                    },
                    thread_role="audit",
                )
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {
                        "type": "auto_review_completed",
                        "node_id": node_id,
                        "overall_severity": severity,
                        "overall_score": score,
                        "summary": review_result["summary"],
                    },
                    thread_role="audit",
                )

            self._auto_accept_local_review(project_id=project_id, node_id=node_id)

        except Exception as exc:
            logger.debug(
                "Auto-review failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )
            try:
                with draft_lock:
                    accumulator.finalize()
                    error_parts = accumulator.snapshot_parts()
                    streamed_content = accumulator.content_projection()

                now = iso_now()
                with self._storage.project_lock(project_id):
                    exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
                    if exec_state is not None:
                        auto_review = exec_state.get("auto_review") or {}
                        auto_review.update({
                            "status": "failed",
                            "completed_at": now,
                            "error_message": str(exc),
                        })
                        exec_state["auto_review"] = auto_review
                        self._storage.execution_state_store.write_state(project_id, node_id, exec_state)

                persisted = self._persist_auto_review_message(
                    project_id=project_id,
                    node_id=node_id,
                    turn_id=turn_id,
                    assistant_message_id=assistant_message_id,
                    content=streamed_content,
                    status="error",
                    error=str(exc),
                    thread_id=thread_id,
                    clear_active_turn=True,
                    parts=error_parts,
                    items=accumulator.snapshot_items(),
                )
            except Exception:
                persisted = False
                logger.debug("Failed to persist auto-review error state", exc_info=True)

            if persisted:
                self._chat_event_broker.publish(
                    project_id,
                    node_id,
                    {"type": "assistant_error", "message_id": assistant_message_id, "error": str(exc)},
                    thread_role="audit",
                )
            self._chat_event_broker.publish(
                project_id,
                node_id,
                {"type": "auto_review_failed", "node_id": node_id, "error": str(exc)},
                thread_role="audit",
            )
        finally:
            if self._chat_service is not None:
                self._chat_service.clear_external_live_turn(
                    project_id, node_id, "audit", turn_id
                )

    def _auto_accept_local_review(self, *, project_id: str, node_id: str) -> None:
        if self._review_service is None:
            logger.debug(
                "Skipping auto-accept for %s/%s: review_service unavailable.",
                project_id,
                node_id,
            )
            return

        try:
            exec_state = self._storage.execution_state_store.read_state(project_id, node_id)
            if exec_state is None or exec_state.get("status") != "completed":
                logger.debug(
                    "Skipping auto-accept for %s/%s: execution status is not 'completed'.",
                    project_id,
                    node_id,
                )
                return

            auto_review = exec_state.get("auto_review") or {}
            checkpoint_summary = str(auto_review.get("checkpoint_summary") or "").strip()
            overall_severity = str(auto_review.get("overall_severity") or "info").strip()
            overall_score = auto_review.get("overall_score")
            score_str = str(overall_score) if isinstance(overall_score, int) else "?"
            full_summary = f"[Auto-reviewed: {overall_severity}/{score_str}] {checkpoint_summary}"

            self._review_service.start_local_review(project_id, node_id)
            response = self._review_service.accept_local_review(project_id, node_id, full_summary)
            activated_sibling_id = response.get("activated_sibling_id")

            self._chat_event_broker.publish(
                project_id,
                node_id,
                {
                    "type": "auto_review_accepted",
                    "node_id": node_id,
                    "activated_sibling_id": activated_sibling_id,
                },
                thread_role="audit",
            )
        except Exception as exc:
            logger.warning(
                "Auto-accept failed for %s/%s: %s",
                project_id,
                node_id,
                exc,
                exc_info=True,
            )

    def _persist_auto_review_message(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        content: str,
        status: str,
        error: str | None,
        thread_id: str | None,
        clear_active_turn: bool,
        parts: list[dict[str, Any]] | None = None,
        items: list[dict[str, Any]] | None = None,
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id, node_id, thread_role="audit"
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False
            message = None
            for candidate in reversed(session.get("messages", [])):
                if candidate.get("message_id") == assistant_message_id:
                    message = candidate
                    break
            if message is None:
                return False

            message["content"] = content
            message["status"] = status
            message["error"] = error
            message["updated_at"] = iso_now()
            if parts is not None:
                message["parts"] = parts
            if items is not None:
                message["items"] = items
            if thread_id is not None:
                session["thread_id"] = thread_id
            if clear_active_turn:
                session["active_turn_id"] = None

            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role="audit"
            )
            return True

    def _persist_auto_review_thread_id(
        self,
        *,
        project_id: str,
        node_id: str,
        turn_id: str,
        assistant_message_id: str,
        thread_id: str,
    ) -> bool:
        with self._storage.project_lock(project_id):
            session = self._storage.chat_state_store.read_session(
                project_id, node_id, thread_role="audit"
            )
            if str(session.get("active_turn_id") or "") != turn_id:
                return False
            msg_found = any(
                m.get("message_id") == assistant_message_id
                for m in session.get("messages", [])
            )
            if not msg_found:
                return False
            session["thread_id"] = thread_id
            self._storage.chat_state_store.write_session(
                project_id, node_id, session, thread_role="audit"
            )
            return True
