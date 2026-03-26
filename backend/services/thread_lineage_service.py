from __future__ import annotations

from typing import Any

from backend.ai.codex_client import CodexAppClient, CodexTransportError
from backend.ai.review_rollup_prompt_builder import build_review_rollup_base_instructions
from backend.services.tree_service import TreeService
from backend.storage.storage import Storage

_RESUME_TIMEOUT_SEC = 15
_THREAD_TIMEOUT_SEC = 30


class ThreadLineageService:
    def __init__(
        self,
        storage: Storage,
        codex_client: CodexAppClient,
        tree_service: TreeService,
    ) -> None:
        self._storage = storage
        self._codex_client = codex_client
        self._tree_service = tree_service

    def ensure_root_audit_thread(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot, node, _ = self._load_snapshot_and_node_locked(project_id, node_id)
            if not self._is_root_node(snapshot, node):
                raise ValueError(f"Node {node_id!r} is not the root node.")

            session = self._storage.chat_state_store.read_session(project_id, node_id, thread_role="audit")
            thread_id = self._normalize_thread_id(session)
            if thread_id:
                resumed = self._resume_existing_thread(
                    thread_id,
                    cwd=workspace_root,
                    writable_roots=None,
                )
                if resumed:
                    if self._needs_legacy_backfill(session):
                        return self._persist_session_locked(
                            project_id,
                            node_id,
                            "audit",
                            session=session,
                            thread_id=thread_id,
                            fork_reason="legacy_resumed",
                            lineage_root_thread_id=thread_id,
                        )
                    return session

            new_thread_id = self._start_thread(
                cwd=workspace_root,
                base_instructions=self._build_audit_base_instructions(snapshot, node),
            )
            return self._persist_session_locked(
                project_id,
                node_id,
                "audit",
                session=session,
                thread_id=new_thread_id,
                forked_from_thread_id=None,
                forked_from_node_id=None,
                forked_from_role=None,
                fork_reason="root_bootstrap",
                lineage_root_thread_id=new_thread_id,
            )

    def ensure_forked_thread(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        source_node_id: str,
        source_role: str,
        fork_reason: str,
        workspace_root: str | None,
        *,
        base_instructions: str | None = None,
        dynamic_tools: list[dict[str, Any]] | None = None,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            self._load_snapshot_and_node_locked(project_id, node_id)
            source_session = self._resolve_source_session_locked(
                project_id,
                source_node_id,
                source_role,
                workspace_root,
            )
            source_thread_id = self._normalize_thread_id(source_session)
            if not source_thread_id:
                raise ValueError(
                    f"Source session {source_node_id!r}/{source_role!r} does not have a thread id."
                )

            target_session = self._storage.chat_state_store.read_session(
                project_id,
                node_id,
                thread_role=thread_role,
            )
            existing_thread_id = self._normalize_thread_id(target_session)
            if existing_thread_id:
                resumed = self._resume_existing_thread(
                    existing_thread_id,
                    cwd=workspace_root,
                    writable_roots=writable_roots,
                )
                if resumed:
                    if self._needs_legacy_backfill(target_session):
                        lineage_root_thread_id = self._normalize_optional_string(
                            target_session.get("lineage_root_thread_id")
                        )
                        return self._persist_session_locked(
                            project_id,
                            node_id,
                            thread_role,
                            session=target_session,
                            thread_id=existing_thread_id,
                            fork_reason="legacy_resumed",
                            lineage_root_thread_id=lineage_root_thread_id,
                        )
                    return target_session

            lineage_root_thread_id = self._normalize_optional_string(
                source_session.get("lineage_root_thread_id")
            )
            new_thread_id = self._fork_thread(
                source_thread_id,
                cwd=workspace_root,
                base_instructions=base_instructions,
                dynamic_tools=dynamic_tools,
                writable_roots=writable_roots,
            )
            return self._persist_session_locked(
                project_id,
                node_id,
                thread_role,
                session=target_session,
                thread_id=new_thread_id,
                forked_from_thread_id=source_thread_id,
                forked_from_node_id=source_node_id,
                forked_from_role=source_role,
                fork_reason=fork_reason,
                lineage_root_thread_id=lineage_root_thread_id,
            )

    def resume_or_rebuild_session(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        workspace_root: str | None,
        *,
        base_instructions: str | None = None,
        dynamic_tools: list[dict[str, Any]] | None = None,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot, node, _ = self._load_snapshot_and_node_locked(project_id, node_id)
            session = self._storage.chat_state_store.read_session(
                project_id,
                node_id,
                thread_role=thread_role,
            )
            thread_id = self._normalize_thread_id(session)
            if not thread_id:
                return self.rebuild_from_ancestor(
                    project_id,
                    node_id,
                    thread_role,
                    workspace_root,
                    base_instructions=base_instructions,
                    dynamic_tools=dynamic_tools,
                    writable_roots=writable_roots,
                )

            try:
                self._codex_client.resume_thread(
                    thread_id,
                    cwd=workspace_root,
                    timeout_sec=_RESUME_TIMEOUT_SEC,
                    writable_roots=writable_roots,
                )
            except CodexTransportError as exc:
                if not self._is_missing_thread_error(exc):
                    raise
                return self.rebuild_from_ancestor(
                    project_id,
                    node_id,
                    thread_role,
                    workspace_root,
                    base_instructions=base_instructions,
                    dynamic_tools=dynamic_tools,
                    writable_roots=writable_roots,
                )

            if self._needs_legacy_backfill(session):
                lineage_root_thread_id = self._normalize_optional_string(
                    session.get("lineage_root_thread_id")
                )
                if thread_role == "audit" and self._is_root_node(snapshot, node):
                    lineage_root_thread_id = thread_id
                return self._persist_session_locked(
                    project_id,
                    node_id,
                    thread_role,
                    session=session,
                    thread_id=thread_id,
                    fork_reason="legacy_resumed",
                    lineage_root_thread_id=lineage_root_thread_id,
                )
            return session

    def rebuild_from_ancestor(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        workspace_root: str | None,
        *,
        base_instructions: str | None = None,
        dynamic_tools: list[dict[str, Any]] | None = None,
        writable_roots: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._storage.project_lock(project_id):
            snapshot, node, node_by_id = self._load_snapshot_and_node_locked(project_id, node_id)
            if thread_role == "audit" and self._is_root_node(snapshot, node):
                return self.ensure_root_audit_thread(project_id, node_id, workspace_root)

            if thread_role in {"ask_planning", "execution"}:
                self._ensure_audit_exists(project_id, node_id, workspace_root)
                return self._fork_target_from_source_locked(
                    project_id,
                    node_id,
                    thread_role,
                    source_node_id=node_id,
                    source_role="audit",
                    fork_reason=self._fork_reason_for_role(thread_role),
                    workspace_root=workspace_root,
                    base_instructions=base_instructions,
                    dynamic_tools=dynamic_tools,
                    writable_roots=writable_roots,
                )

            if thread_role == "audit" and str(node.get("node_kind") or "").strip() == "review":
                parent_id = self._normalize_optional_string(node.get("parent_id"))
                if not parent_id:
                    raise ValueError(f"Review node {node_id!r} is missing a parent.")
                self._ensure_audit_exists(project_id, parent_id, workspace_root)
                return self._fork_target_from_source_locked(
                    project_id,
                    node_id,
                    "audit",
                    source_node_id=parent_id,
                    source_role="audit",
                    fork_reason="review_bootstrap",
                    workspace_root=workspace_root,
                    base_instructions=self._review_audit_base_instructions(
                        node,
                        base_instructions,
                    ),
                    dynamic_tools=dynamic_tools,
                    writable_roots=writable_roots,
                )

            if thread_role == "audit":
                review_node_id = self._review_node_id_for_child(node, node_by_id)
                if review_node_id:
                    return self._ensure_child_audit_from_review_locked(
                        project_id,
                        node_id,
                        review_node_id,
                        workspace_root,
                        base_instructions=base_instructions,
                        dynamic_tools=dynamic_tools,
                        writable_roots=writable_roots,
                    )
                return self._ensure_audit_exists(project_id, node_id, workspace_root)

            raise ValueError(f"Unsupported thread role for rebuild: {thread_role!r}")

    def _ensure_audit_exists(
        self,
        project_id: str,
        node_id: str,
        workspace_root: str | None,
    ) -> dict[str, Any]:
        snapshot, node, node_by_id = self._load_snapshot_and_node_locked(project_id, node_id)
        session = self._storage.chat_state_store.read_session(project_id, node_id, thread_role="audit")
        thread_id = self._normalize_thread_id(session)

        if self._is_root_node(snapshot, node):
            return self.ensure_root_audit_thread(project_id, node_id, workspace_root)

        if thread_id:
            if self._needs_legacy_backfill(session):
                return self._persist_session_locked(
                    project_id,
                    node_id,
                    "audit",
                    session=session,
                    thread_id=thread_id,
                    fork_reason="legacy_resumed",
                    lineage_root_thread_id=self._normalize_optional_string(
                        session.get("lineage_root_thread_id")
                    ),
                )
            return session

        if str(node.get("node_kind") or "").strip() == "review":
            parent_id = self._normalize_optional_string(node.get("parent_id"))
            if not parent_id:
                raise ValueError(f"Review node {node_id!r} is missing a parent.")
            self._ensure_audit_exists(project_id, parent_id, workspace_root)
            return self._fork_target_from_source_locked(
                project_id,
                node_id,
                "audit",
                source_node_id=parent_id,
                source_role="audit",
                fork_reason="review_bootstrap",
                workspace_root=workspace_root,
                base_instructions=self._review_audit_base_instructions(node, None),
                dynamic_tools=None,
                writable_roots=None,
            )

        review_node_id = self._review_node_id_for_child(node, node_by_id)
        if review_node_id:
            return self._ensure_child_audit_from_review_locked(
                project_id,
                node_id,
                review_node_id,
                workspace_root,
                base_instructions=None,
                dynamic_tools=None,
                writable_roots=None,
            )

        root_id = self._root_node_id(snapshot)
        if not root_id:
            raise ValueError(f"Project {project_id!r} is missing a root node.")

        root_session = self.ensure_root_audit_thread(project_id, root_id, workspace_root)
        root_thread_id = self._normalize_thread_id(root_session)
        if not root_thread_id:
            raise ValueError("Root audit bootstrap did not produce a thread id.")

        self._load_snapshot_and_node_locked(project_id, node_id)
        new_thread_id = self._start_thread(
            cwd=workspace_root,
            base_instructions=self._build_audit_base_instructions(snapshot, node),
        )
        return self._persist_session_locked(
            project_id,
            node_id,
            "audit",
            session=session,
            thread_id=new_thread_id,
            forked_from_thread_id=None,
            forked_from_node_id=None,
            forked_from_role=None,
            fork_reason="audit_lazy_bootstrap",
            lineage_root_thread_id=root_thread_id,
        )

    def _review_node_id_for_child(
        self,
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> str | None:
        parent_id = self._normalize_optional_string(node.get("parent_id"))
        parent = node_by_id.get(parent_id) if parent_id else None
        if not isinstance(parent, dict):
            return None
        return self._normalize_optional_string(parent.get("review_node_id"))

    def _ensure_child_audit_from_review_locked(
        self,
        project_id: str,
        node_id: str,
        review_node_id: str,
        workspace_root: str | None,
        *,
        base_instructions: str | None,
        dynamic_tools: list[dict[str, Any]] | None,
        writable_roots: list[str] | None,
    ) -> dict[str, Any]:
        self.resume_or_rebuild_session(
            project_id,
            review_node_id,
            "audit",
            workspace_root,
            writable_roots=writable_roots,
        )
        return self._fork_target_from_source_locked(
            project_id,
            node_id,
            "audit",
            source_node_id=review_node_id,
            source_role="audit",
            fork_reason="child_activation",
            workspace_root=workspace_root,
            base_instructions=base_instructions,
            dynamic_tools=dynamic_tools,
            writable_roots=writable_roots,
        )

    def _load_snapshot_and_node_locked(
        self,
        project_id: str,
        node_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]]]:
        snapshot = self._storage.project_store.load_snapshot(project_id)
        node_by_id = self._tree_service.node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise ValueError(f"Node {node_id!r} was not found in project {project_id!r}.")
        return snapshot, node, node_by_id

    def _build_audit_base_instructions(
        self,
        snapshot: dict[str, Any],
        node: dict[str, Any],
    ) -> str:
        project = snapshot.get("project", {})
        project_name = self._normalize_optional_string(project.get("name")) or "PlanningTree project"
        root_goal = self._normalize_optional_string(project.get("root_goal"))
        node_title = self._normalize_optional_string(node.get("title")) or "Untitled task"
        node_description = self._normalize_optional_string(node.get("description"))
        node_kind = self._normalize_optional_string(node.get("node_kind")) or "original"

        lines = [
            "You are the canonical audit assistant for a PlanningTree task thread.",
            "This audit thread is the stable lineage source for downstream forks at this node.",
            f"Project: {project_name}",
            f"Task kind: {node_kind}",
            f"Task title: {node_title}",
        ]
        if root_goal:
            lines.append(f"Root goal: {root_goal}")
        if node_description:
            lines.append(f"Task description: {node_description}")
        lines.extend(
            [
                "Canonical artifacts such as frame, spec, execution state, checkpoints, and rollup results live in local storage.",
                "Do not rely on synthetic thread history as the source of truth for canonical artifacts.",
            ]
        )
        return "\n".join(lines)

    def _review_audit_base_instructions(
        self,
        node: dict[str, Any],
        base_instructions: str | None,
    ) -> str | None:
        if base_instructions is not None:
            return base_instructions
        if self._normalize_optional_string(node.get("node_kind")) == "review":
            return build_review_rollup_base_instructions()
        return None

    def _persist_session_locked(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        *,
        session: dict[str, Any] | None = None,
        thread_id: str | None = None,
        forked_from_thread_id: str | None = None,
        forked_from_node_id: str | None = None,
        forked_from_role: str | None = None,
        fork_reason: str | None = None,
        lineage_root_thread_id: str | None = None,
    ) -> dict[str, Any]:
        payload = dict(
            session
            if isinstance(session, dict)
            else self._storage.chat_state_store.read_session(project_id, node_id, thread_role=thread_role)
        )
        payload["thread_role"] = thread_role
        if thread_id is not None:
            payload["thread_id"] = thread_id
        if "active_turn_id" not in payload:
            payload["active_turn_id"] = None
        if "messages" not in payload:
            payload["messages"] = []
        payload["forked_from_thread_id"] = forked_from_thread_id
        payload["forked_from_node_id"] = forked_from_node_id
        payload["forked_from_role"] = forked_from_role
        payload["fork_reason"] = fork_reason
        payload["lineage_root_thread_id"] = lineage_root_thread_id
        return self._storage.chat_state_store.write_session(
            project_id,
            node_id,
            payload,
            thread_role=thread_role,
        )

    def _resolve_source_session_locked(
        self,
        project_id: str,
        source_node_id: str,
        source_role: str,
        workspace_root: str | None,
    ) -> dict[str, Any]:
        if source_role == "audit":
            return self._ensure_audit_exists(project_id, source_node_id, workspace_root)
        return self._storage.chat_state_store.read_session(
            project_id,
            source_node_id,
            thread_role=source_role,
        )

    def _fork_target_from_source_locked(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
        *,
        source_node_id: str,
        source_role: str,
        fork_reason: str,
        workspace_root: str | None,
        base_instructions: str | None,
        dynamic_tools: list[dict[str, Any]] | None,
        writable_roots: list[str] | None,
    ) -> dict[str, Any]:
        source_session = self._resolve_source_session_locked(
            project_id,
            source_node_id,
            source_role,
            workspace_root,
        )
        source_thread_id = self._normalize_thread_id(source_session)
        if not source_thread_id:
            raise ValueError(
                f"Source session {source_node_id!r}/{source_role!r} does not have a thread id."
            )
        target_session = self._storage.chat_state_store.read_session(
            project_id,
            node_id,
            thread_role=thread_role,
        )
        lineage_root_thread_id = self._normalize_optional_string(
            source_session.get("lineage_root_thread_id")
        )
        new_thread_id = self._fork_thread(
            source_thread_id,
            cwd=workspace_root,
            base_instructions=base_instructions,
            dynamic_tools=dynamic_tools,
            writable_roots=writable_roots,
        )
        return self._persist_session_locked(
            project_id,
            node_id,
            thread_role,
            session=target_session,
            thread_id=new_thread_id,
            forked_from_thread_id=source_thread_id,
            forked_from_node_id=source_node_id,
            forked_from_role=source_role,
            fork_reason=fork_reason,
            lineage_root_thread_id=lineage_root_thread_id,
        )

    def _resume_existing_thread(
        self,
        thread_id: str,
        *,
        cwd: str | None,
        writable_roots: list[str] | None,
    ) -> bool:
        try:
            self._codex_client.resume_thread(
                thread_id,
                cwd=cwd,
                timeout_sec=_RESUME_TIMEOUT_SEC,
                writable_roots=writable_roots,
            )
            return True
        except CodexTransportError as exc:
            if self._is_missing_thread_error(exc):
                return False
            raise

    def _start_thread(
        self,
        *,
        cwd: str | None,
        base_instructions: str | None,
        dynamic_tools: list[dict[str, Any]] | None = None,
        writable_roots: list[str] | None = None,
    ) -> str:
        response = self._codex_client.start_thread(
            cwd=cwd,
            timeout_sec=_THREAD_TIMEOUT_SEC,
            base_instructions=base_instructions,
            dynamic_tools=dynamic_tools,
            writable_roots=writable_roots,
        )
        return self._require_thread_id(response)

    def _fork_thread(
        self,
        source_thread_id: str,
        *,
        cwd: str | None,
        base_instructions: str | None,
        dynamic_tools: list[dict[str, Any]] | None,
        writable_roots: list[str] | None,
    ) -> str:
        response = self._codex_client.fork_thread(
            source_thread_id,
            cwd=cwd,
            timeout_sec=_THREAD_TIMEOUT_SEC,
            base_instructions=base_instructions,
            dynamic_tools=dynamic_tools,
            writable_roots=writable_roots,
        )
        return self._require_thread_id(response)

    def _require_thread_id(self, response: dict[str, Any]) -> str:
        thread_id = self._normalize_optional_string(response.get("thread_id"))
        if not thread_id:
            raise ValueError("Codex thread operation did not return a thread id.")
        return thread_id

    def _root_node_id(self, snapshot: dict[str, Any]) -> str | None:
        return self._normalize_optional_string(snapshot.get("tree_state", {}).get("root_node_id"))

    def _is_root_node(self, snapshot: dict[str, Any], node: dict[str, Any]) -> bool:
        node_id = self._normalize_optional_string(node.get("node_id"))
        if not node_id:
            return False
        root_id = self._root_node_id(snapshot)
        if root_id and node_id == root_id:
            return True
        return self._normalize_optional_string(node.get("node_kind")) == "root"

    def _fork_reason_for_role(self, thread_role: str) -> str:
        if thread_role == "ask_planning":
            return "ask_bootstrap"
        if thread_role == "execution":
            return "execution_bootstrap"
        raise ValueError(f"No default fork reason for thread role {thread_role!r}.")

    def _needs_legacy_backfill(self, session: dict[str, Any]) -> bool:
        return self._normalize_thread_id(session) is not None and not self._has_lineage_metadata(session)

    def _has_lineage_metadata(self, session: dict[str, Any]) -> bool:
        for key in (
            "forked_from_thread_id",
            "forked_from_node_id",
            "forked_from_role",
            "fork_reason",
            "lineage_root_thread_id",
        ):
            if self._normalize_optional_string(session.get(key)) is not None:
                return True
        return False

    def _normalize_thread_id(self, session: dict[str, Any] | None) -> str | None:
        if not isinstance(session, dict):
            return None
        return self._normalize_optional_string(session.get("thread_id"))

    def _normalize_optional_string(self, value: Any) -> str | None:
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _is_missing_thread_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "no rollout found for thread id" in message or "thread not found" in message
