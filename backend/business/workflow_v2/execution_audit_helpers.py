from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, TypedDict

from backend.ai.split_context_builder import build_split_context
from backend.errors.app_errors import FinishTaskNotAllowed, NodeNotFound, ReviewNotAllowed
from backend.services.finish_task_service import FinishTaskService
from backend.services.git_checkpoint_service import GitCheckpointService
from backend.services.tree_service import TreeService
from backend.services.workspace_sha import compute_workspace_sha
from backend.storage.file_utils import iso_now

logger = logging.getLogger(__name__)


class WorkspaceCommitResult(TypedDict):
    initialSha: str
    headSha: str
    commitMessage: str
    committed: bool


class WorkflowMetadataService:
    def __init__(self, tree_service: TreeService, finish_task_service: FinishTaskService) -> None:
        self._tree_service = tree_service
        self._finish_task_service = finish_task_service

    def load_execution_metadata(
        self,
        project_id: str,
        node_id: str,
        *,
        validate_finish_task: bool = False,
    ) -> dict[str, Any]:
        snapshot = self._finish_task_service._storage.project_store.load_snapshot(project_id)
        node_by_id = self._tree_service.node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise NodeNotFound(node_id)
        node_dir = self._finish_task_service._resolve_node_dir(snapshot, node_id)
        if validate_finish_task:
            spec_content = self._finish_task_service._validate_finish_task_locked(
                project_id,
                node_id,
                snapshot,
                node,
                node_dir,
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
            "frameContent": self._finish_task_service._load_confirmed_frame_content(node_dir),
            "taskContext": build_split_context(snapshot, node, node_by_id),
            "workspaceRoot": self._finish_task_service._workspace_root_from_snapshot(snapshot),
            "initialSha": self._finish_task_service._compute_initial_sha(project_id, node_id, snapshot),
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
        return f"{base}\n\n{follow_up}"

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
