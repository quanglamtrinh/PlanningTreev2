from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, TypedDict

from uuid import uuid4

from backend.ai.split_context_builder import build_split_context
from backend.errors.app_errors import FinishTaskNotAllowed, NodeNotFound
from backend.services import planningtree_workspace
from backend.services.node_detail_service import _load_spec_meta_from_node_dir
from backend.services.git_checkpoint_service import GitCheckpointService
from backend.services.tree_service import TreeService
from backend.services.workspace_sha import compute_workspace_sha
from backend.storage.file_utils import iso_now, load_json

logger = logging.getLogger(__name__)


class WorkspaceCommitResult(TypedDict):
    initialSha: str
    headSha: str
    commitMessage: str
    committed: bool


class WorkflowMetadataService:
    def __init__(self, storage: Any, tree_service: TreeService, git_checkpoint_service: GitCheckpointService | None) -> None:
        self._storage = storage
        self._tree_service = tree_service
        self._git_checkpoint_service = git_checkpoint_service

    def load_execution_metadata(
        self,
        project_id: str,
        node_id: str,
        *,
        validate_finish_task: bool = False,
    ) -> dict[str, Any]:
        snapshot = self._storage.project_store.load_snapshot(project_id)
        node_by_id = self._tree_service.node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise NodeNotFound(node_id)
        node_dir = resolve_node_dir(snapshot, node_id)
        if validate_finish_task:
            spec_content = validate_execution_ready(
                storage=self._storage,
                git_checkpoint_service=self._git_checkpoint_service,
                project_id=project_id,
                node_id=node_id,
                snapshot=snapshot,
                node=node,
                node_dir=node_dir,
            )
        else:
            spec_path = node_dir / "spec.md"
            spec_content = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
            if not spec_content.strip():
                raise FinishTaskNotAllowed("Spec must be non-empty before execution can run.")
        return {
            "snapshot": snapshot,
            "node": node,
            "nodeById": node_by_id,
            "specContent": spec_content,
            "frameContent": load_confirmed_frame_content(node_dir),
            "taskContext": build_split_context(snapshot, node, node_by_id),
            "workspaceRoot": workspace_root_from_snapshot(snapshot),
            "initialSha": compute_initial_sha(self._git_checkpoint_service, snapshot),
        }

    @staticmethod
    def build_execution_start_prompt() -> str:
        return (
            "Implement the confirmed task in this workspace now.\n"
            "The complete task context has already been injected into this execution thread.\n"
            "Do not ask clarifying questions.\n"
            "Make concrete changes, verify results, and then summarize what changed."
        )

    @staticmethod
    def build_execution_followup_prompt(
        *,
        spec_content: str,
        frame_content: str,
        task_context: dict[str, Any],
        instruction_text: str,
    ) -> str:
        del spec_content, frame_content, task_context
        follow_up = (
            "Execution follow-up request:\n"
            "```text\n"
            f"{instruction_text.strip()}\n"
            "```\n\n"
            "Apply this follow-up incrementally on top of the current workspace. "
            "Do not ask for clarification. Keep working toward the same confirmed task."
        )
        return follow_up

    @staticmethod
    def build_improve_prompt(
        *,
        spec_content: str,
        frame_content: str,
        task_context: dict[str, Any],
        review_text: str,
    ) -> str:
        del spec_content, frame_content, task_context
        improve = (
            "The execution/audit context is already available in this thread.\n"
            "Apply the review feedback below directly in the workspace.\n\n"
            "Latest local review feedback:\n"
            "```markdown\n"
            f"{review_text.strip()}\n"
            "```\n\n"
            "Improve the implementation to address this review feedback now. "
            "Keep the solution aligned with the confirmed task and existing codebase."
        )
        return improve

    @staticmethod
    def _truncate_for_prompt(text: str, *, char_limit: int) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return ""
        if len(normalized) <= char_limit:
            return normalized
        if char_limit <= 3:
            return normalized[:char_limit]
        return normalized[: char_limit - 3].rstrip() + "..."

    @classmethod
    def build_audit_review_prompt(
        cls,
        *,
        node: dict[str, Any],
        spec_content: str,
        frame_content: str,
        review_commit_sha: str,
    ) -> str:
        del spec_content, frame_content
        task_number = str(node.get("hierarchical_number") or "").strip()
        task_title = str(node.get("title") or "").strip() or "Task"
        task_label = f"{task_number} {task_title}".strip()

        sections = [
            "You are reviewing code changes that were just completed in the current workspace.\n",
            "The complete task context has already been injected into this audit thread.\n\n",
            "I just completed code for task:\n",
            f"- {task_label}\n\n",
            f"The commit hash is `{review_commit_sha}`.\n",
            "Please review this implementation.\n",
            "Do you have any questions or issues?\n\n",
            "Review requirements:\n",
            "1. Evaluate strictly against the confirmed spec/frame already present in thread context.\n",
            "2. Prioritize bugs, regressions, missing tests, and maintainability risks.\n",
            "3. Ignore changes under `.planningtree/`.\n",
            "4. If there are no serious issues, state that explicitly.\n",
            "5. Include concrete file paths for findings whenever possible.\n",
            f"6. Start by inspecting commit `{review_commit_sha}` and its related diffs.\n",
            "7. Respond in plain markdown prose for humans.\n",
            "8. Do NOT return JSON/YAML objects or fenced data payloads.\n",
        ]
        return "".join(sections)


class WorkflowProgressionService:
    def __init__(self, storage: Any, tree_service: TreeService) -> None:
        self._storage = storage
        self._tree_service = tree_service

    def complete_node(
        self,
        project_id: str,
        node_id: str,
        *,
        accepted_sha: str,
        summary_text: str | None,
    ) -> dict[str, str | None]:
        activated_sibling_id: str | None = None
        activated_review_node_id: str | None = None
        activated_workspace_root: str | None = None
        rollup_ready_review_node_id: str | None = None

        with self._storage.project_lock(project_id):
            snapshot = self._storage.project_store.load_snapshot(project_id)
            node_by_id = self._tree_service.node_index(snapshot)
            node = node_by_id.get(node_id)
            if node is None:
                raise NodeNotFound(node_id)
            node["status"] = "done"
            parent_id = str(node.get("parent_id") or "").strip()
            parent = node_by_id.get(parent_id) if parent_id else None
            review_node_id = str(parent.get("review_node_id") or "").strip() if isinstance(parent, dict) else ""
            if review_node_id:
                self._storage.workflow_domain_store.add_review_checkpoint(
                    project_id,
                    review_node_id,
                    sha=accepted_sha,
                    summary=summary_text,
                    source_node_id=node_id,
                )
                activated_review_node_id = review_node_id
                activated_sibling_id, rollup_ready_review_node_id = self._try_activate_next_sibling(
                    project_id,
                    parent,
                    review_node_id,
                    snapshot,
                    node_by_id,
                )
                if activated_sibling_id:
                    activated_workspace_root = workspace_root_from_snapshot(snapshot)
            elif isinstance(parent, dict):
                unlocked_id = self._tree_service.unlock_next_sibling(node, node_by_id)
                if unlocked_id:
                    snapshot["tree_state"]["active_node_id"] = unlocked_id
                    activated_sibling_id = unlocked_id

            now = iso_now()
            snapshot["updated_at"] = now
            self._storage.project_store.save_snapshot(project_id, snapshot)
            self._storage.project_store.touch_meta(project_id, now)

        return {
            "activatedSiblingId": activated_sibling_id,
            "activatedReviewNodeId": activated_review_node_id,
            "activatedWorkspaceRoot": activated_workspace_root,
            "rollupReadyReviewNodeId": rollup_ready_review_node_id,
        }

    def _try_activate_next_sibling(
        self,
        project_id: str,
        parent: dict[str, Any],
        review_node_id: str,
        snapshot: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> tuple[str | None, str | None]:
        next_sib = self._storage.workflow_domain_store.get_next_pending_sibling(project_id, review_node_id)
        if next_sib is None:
            if self._try_mark_rollup_ready(project_id, parent, review_node_id, node_by_id):
                return None, review_node_id
            return None, None
        return self._materialize_sibling(project_id, parent, review_node_id, next_sib, snapshot, node_by_id), None

    def _materialize_sibling(
        self,
        project_id: str,
        parent: dict[str, Any],
        review_node_id: str,
        manifest_entry: dict[str, Any],
        snapshot: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> str:
        now = iso_now()
        parent_id = str(parent.get("node_id") or "")
        parent_hnum = str(parent.get("hierarchical_number") or "1")
        parent_depth = int(parent.get("depth", 0) or 0)
        sib_index = int(manifest_entry["index"])
        new_node_id = uuid4().hex
        new_node = {
            "node_id": new_node_id,
            "parent_id": parent_id,
            "child_ids": [],
            "title": manifest_entry["title"],
            "description": manifest_entry["objective"],
            "status": "ready",
            "node_kind": "original",
            "depth": parent_depth + 1,
            "display_order": sib_index - 1,
            "hierarchical_number": f"{parent_hnum}.{sib_index}",
            "created_at": now,
        }
        parent.setdefault("child_ids", []).append(new_node_id)
        snapshot["tree_state"]["node_index"][new_node_id] = new_node
        node_by_id[new_node_id] = new_node
        snapshot["tree_state"]["active_node_id"] = new_node_id
        self._storage.workflow_domain_store.mark_sibling_materialized(project_id, review_node_id, sib_index, new_node_id)
        workspace_root = workspace_root_from_snapshot(snapshot)
        if workspace_root:
            planningtree_workspace.sync_snapshot_tree(Path(workspace_root), snapshot)
        return new_node_id

    def _try_mark_rollup_ready(
        self,
        project_id: str,
        parent: dict[str, Any],
        review_node_id: str,
        node_by_id: dict[str, dict[str, Any]],
    ) -> bool:
        review_state = self._storage.workflow_domain_store.read_review(project_id, review_node_id)
        if review_state is None:
            return False
        rollup = review_state.get("rollup", {})
        if rollup.get("status") != "pending":
            return False
        for sib in review_state.get("pending_siblings", []):
            if sib.get("materialized_node_id") is None:
                return False
        for child_id in parent.get("child_ids", []):
            child = node_by_id.get(child_id)
            if child is None:
                return False
            exec_state = self._storage.workflow_domain_store.read_execution(project_id, child_id)
            if exec_state is None or exec_state.get("status") != "review_accepted":
                return False
        self._storage.workflow_domain_store.set_review_rollup(project_id, review_node_id, "ready")
        return True


def validate_execution_ready(
    *,
    storage: Any,
    git_checkpoint_service: GitCheckpointService | None,
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
    if len(node.get("child_ids") or []) > 0:
        raise FinishTaskNotAllowed("Finish Task is only available for leaf nodes (no children).")
    node_status = node.get("status", "")
    if node_status not in ("ready", "in_progress"):
        raise FinishTaskNotAllowed(f"Node status must be 'ready' or 'in_progress', got '{node_status}'.")
    exec_state = storage.workflow_domain_store.read_execution(project_id, node_id)
    if exec_state is not None:
        status = exec_state.get("status")
        if status == "executing":
            raise FinishTaskNotAllowed("Execution is already in progress for this node.")
        if status != "failed" and status is not None and status != "idle":
            raise FinishTaskNotAllowed("Execution has already been started for this node.")
    spec_path = node_dir / planningtree_workspace.SPEC_FILE_NAME
    spec_content = spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""
    if not spec_content.strip():
        raise FinishTaskNotAllowed("Spec must be non-empty before Finish Task.")
    if git_checkpoint_service is not None:
        workspace_root = workspace_root_from_snapshot(snapshot)
        if workspace_root:
            expected_head = resolve_expected_baseline_sha(storage, git_checkpoint_service, project_id, node_id, snapshot)
            blockers = git_checkpoint_service.validate_guardrails(Path(workspace_root), expected_head=expected_head)
            if blockers:
                raise FinishTaskNotAllowed(blockers[0])
    return spec_content


def resolve_expected_baseline_sha(
    storage: Any,
    git_checkpoint_service: GitCheckpointService,
    project_id: str,
    node_id: str,
    snapshot: dict[str, Any],
) -> str | None:
    node_index = snapshot.get("tree_state", {}).get("node_index", {})
    node = node_index.get(node_id, {})
    parent_id = node.get("parent_id")
    if not parent_id:
        return None
    parent = node_index.get(parent_id, {})
    review_node_id = parent.get("review_node_id")
    if not review_node_id:
        return None
    review_state = storage.workflow_domain_store.read_review(project_id, review_node_id)
    if not review_state:
        return None
    checkpoints = review_state.get("checkpoints", [])
    if not checkpoints:
        return None
    latest_sha = checkpoints[-1].get("sha", "")
    if git_checkpoint_service.is_git_commit_sha(latest_sha):
        return latest_sha
    k0_git_head = review_state.get("k0_git_head_sha")
    if git_checkpoint_service.is_git_commit_sha(k0_git_head):
        return k0_git_head
    return None


def compute_initial_sha(git_checkpoint_service: GitCheckpointService | None, snapshot: dict[str, Any]) -> str:
    workspace_root = workspace_root_from_snapshot(snapshot)
    if workspace_root is None:
        raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
    if git_checkpoint_service is not None:
        return git_checkpoint_service.capture_head_sha(Path(workspace_root))
    return compute_workspace_sha(Path(workspace_root))


def load_confirmed_frame_content(node_dir: Path) -> str:
    frame_meta = load_json(node_dir / "frame.meta.json", default=None)
    if not isinstance(frame_meta, dict):
        frame_meta = {}
    frame_content = str(frame_meta.get("confirmed_content") or "")
    if frame_content:
        return frame_content
    frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
    return frame_path.read_text(encoding="utf-8") if frame_path.exists() else ""


def resolve_node_dir(snapshot: dict[str, Any], node_id: str) -> Path:
    workspace_root = workspace_root_from_snapshot(snapshot)
    if not workspace_root:
        raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
    node_dir = planningtree_workspace.resolve_node_dir(Path(workspace_root), snapshot, node_id)
    if node_dir is None:
        raise NodeNotFound(node_id)
    return node_dir


def workspace_root_from_snapshot(snapshot: dict[str, Any]) -> str | None:
    project = snapshot.get("project", {})
    if not isinstance(project, dict):
        return None
    workspace_root = project.get("project_path")
    if isinstance(workspace_root, str) and workspace_root.strip():
        return workspace_root
    return None


class GitArtifactService:
    def __init__(self, git_checkpoint_service: GitCheckpointService | None) -> None:
        self._git_checkpoint_service = git_checkpoint_service

    @staticmethod
    def _is_planningtree_relative_path(path: str | None) -> bool:
        candidate = str(path or "").replace("\\", "/").strip().lower()
        if not candidate:
            return False
        if len(candidate) >= 2 and candidate[1] == ":":
            candidate = candidate[2:]
        candidate = candidate.lstrip("/")
        candidate = re.sub(r"^\./+", "", candidate)
        return candidate == ".planningtree" or candidate.startswith(".planningtree/")

    def compute_workspace_hash(self, workspace_root: str | None) -> str:
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        return compute_workspace_sha(Path(workspace_root).expanduser().resolve())

    def require_workspace_hash(self, workspace_root: str | None, expected_workspace_hash: str) -> str:
        actual = self.compute_workspace_hash(workspace_root)
        if actual != expected_workspace_hash:
            raise FinishTaskNotAllowed(
                f"Workspace drift detected. Expected workspace hash {expected_workspace_hash}, got {actual}."
            )
        return actual

    def require_head_sha(self, workspace_root: str | None, expected_head_sha: str) -> str:
        if self._git_checkpoint_service is None:
            raise ReviewNotAllowed("Git-backed review acceptance is unavailable.")
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            raise ReviewNotAllowed("Project snapshot is missing project_path.")
        actual = self._git_checkpoint_service.capture_head_sha(Path(workspace_root).expanduser().resolve())
        if actual != expected_head_sha:
            raise ReviewNotAllowed(
                f"Workspace HEAD drift detected. Expected {expected_head_sha}, got {actual}."
            )
        return actual

    def commit_workspace(
        self,
        *,
        workspace_root: str | None,
        hierarchical_number: str,
        title: str,
        verb: str,
    ) -> WorkspaceCommitResult:
        if self._git_checkpoint_service is None:
            raise FinishTaskNotAllowed("Git checkpoint service is unavailable.")
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            raise FinishTaskNotAllowed("Project snapshot is missing project_path.")
        project_path = Path(workspace_root).expanduser().resolve()
        initial_sha = self._git_checkpoint_service.capture_head_sha(project_path)
        commit_message = self._git_checkpoint_service.build_commit_message(
            hierarchical_number,
            f"{verb} {title}".strip(),
        )
        committed_sha = self._git_checkpoint_service.commit_if_changed(project_path, commit_message)
        if committed_sha:
            return {
                "initialSha": initial_sha,
                "headSha": committed_sha,
                "commitMessage": commit_message,
                "committed": True,
            }
        return {
            "initialSha": initial_sha,
            "headSha": initial_sha,
            "commitMessage": commit_message,
            "committed": False,
        }

    def get_worktree_diff(
        self,
        *,
        workspace_root: str | None,
        start_sha: str | None,
        paths: list[str] | None = None,
    ) -> str:
        if self._git_checkpoint_service is None:
            return ""
        if not isinstance(workspace_root, str) or not workspace_root.strip():
            return ""
        if not isinstance(start_sha, str) or not start_sha.strip():
            return ""

        project_path = Path(workspace_root).expanduser().resolve()
        normalized_paths: list[str] = []
        for raw_path in paths or []:
            candidate = str(raw_path or "").strip()
            if not candidate:
                continue
            path_obj = Path(candidate)
            if path_obj.is_absolute():
                try:
                    rel = path_obj.expanduser().resolve().relative_to(project_path)
                    normalized_rel = rel.as_posix()
                    if self._is_planningtree_relative_path(normalized_rel):
                        continue
                    normalized_paths.append(normalized_rel)
                    continue
                except Exception:
                    pass
            normalized_path = candidate
            if self._is_planningtree_relative_path(normalized_path):
                continue
            normalized_paths.append(normalized_path)

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
                "Failed to collect worktree diff for %s from %s",
                str(project_path),
                start_sha,
                exc_info=True,
            )
        return ""
