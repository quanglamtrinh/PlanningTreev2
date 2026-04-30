from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from backend.ai.split_context_builder import build_split_context
from backend.business.workflow_v2.context_packets import PlanningTreeContextPacket
from backend.business.workflow_v2.errors import WorkflowThreadBindingFailedError
from backend.business.workflow_v2.models import NodeWorkflowStateV2, ThreadRole
from backend.services import planningtree_workspace
from backend.services.node_detail_service import (
    _load_clarify_from_node_dir,
    _load_frame_meta_from_node_dir,
    _load_spec_meta_from_node_dir,
)
from backend.storage.storage import Storage

_ROLE_PACKET_KIND: dict[str, str] = {
    "ask_planning": "ask_planning_context",
    "execution": "execution_context",
    "audit": "audit_context",
    "package_review": "package_review_context",
}


class WorkflowContextBuilderV2:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def build_context_packet(
        self,
        *,
        project_id: str,
        node_id: str,
        role: ThreadRole,
        workflow_state: NodeWorkflowStateV2 | None = None,
    ) -> PlanningTreeContextPacket:
        snapshot, node, node_by_id, node_dir, workspace_root = self._load_context(project_id, node_id)
        frame_meta = _load_frame_meta_from_node_dir(node_dir)
        spec_meta = _load_spec_meta_from_node_dir(node_dir)
        source_versions = self._source_versions(frame_meta, spec_meta)
        kind = self._packet_kind_for_role(role, snapshot, node, node_by_id)
        payload = self._base_payload(
            snapshot=snapshot,
            node=node,
            node_by_id=node_by_id,
            node_dir=node_dir,
            workspace_root=workspace_root,
            frame_meta=frame_meta,
            spec_meta=spec_meta,
            role=role,
        )

        if role == "audit" and workflow_state is not None:
            payload["executionDecision"] = (
                workflow_state.current_execution_decision.model_dump(by_alias=True, mode="json")
                if workflow_state.current_execution_decision is not None
                else None
            )
            payload["headCommitSha"] = workflow_state.head_commit_sha
            payload["workspaceHash"] = workflow_state.workspace_hash

        if role == "package_review":
            payload["packageReview"] = self._package_review_payload(project_id, snapshot, node, node_by_id)

        return PlanningTreeContextPacket(
            kind=kind,  # type: ignore[arg-type]
            projectId=project_id,
            nodeId=node_id,
            payload=payload,
            sourceVersions=source_versions,
        )

    def build_context_update_packet(
        self,
        *,
        project_id: str,
        node_id: str,
        role: ThreadRole,
        previous_context_packet_hash: str | None,
        next_packet: PlanningTreeContextPacket,
    ) -> PlanningTreeContextPacket:
        return PlanningTreeContextPacket(
            kind="context_update",
            projectId=project_id,
            nodeId=node_id,
            payload={
                "role": role,
                "previousContextPacketHash": previous_context_packet_hash,
                "nextContextPacketHash": next_packet.packet_hash(),
                "nextContext": next_packet.model_dump(by_alias=True, mode="json"),
            },
            sourceVersions=copy.deepcopy(next_packet.source_versions),
        )

    def _load_context(
        self,
        project_id: str,
        node_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, dict[str, Any]], Path, str]:
        snapshot = self._storage.project_store.load_snapshot(project_id)
        node_by_id = self._node_index(snapshot)
        node = node_by_id.get(node_id)
        if node is None:
            raise WorkflowThreadBindingFailedError(
                f"Node {node_id!r} was not found for Workflow V2 context.",
                details={"projectId": project_id, "nodeId": node_id},
            )
        workspace_root = self._workspace_root(snapshot)
        node_dir = planningtree_workspace.resolve_node_dir(Path(workspace_root), snapshot, node_id)
        if node_dir is None:
            raise WorkflowThreadBindingFailedError(
                f"Node directory for {node_id!r} was not found.",
                details={"projectId": project_id, "nodeId": node_id},
            )
        return snapshot, node, node_by_id, node_dir, workspace_root

    @staticmethod
    def _node_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        tree_state = snapshot.get("tree_state")
        if not isinstance(tree_state, dict):
            return {}
        node_index = tree_state.get("node_index")
        if isinstance(node_index, dict):
            return {str(key): value for key, value in node_index.items() if isinstance(value, dict)}
        registry = tree_state.get("node_registry")
        if isinstance(registry, list):
            return {
                str(node.get("node_id")): node
                for node in registry
                if isinstance(node, dict) and str(node.get("node_id") or "").strip()
            }
        return {}

    @staticmethod
    def _workspace_root(snapshot: dict[str, Any]) -> str:
        project = snapshot.get("project")
        if isinstance(project, dict):
            project_path = str(project.get("project_path") or "").strip()
            if project_path:
                return project_path
        raise WorkflowThreadBindingFailedError("Project snapshot is missing project_path.")

    @staticmethod
    def _source_versions(frame_meta: dict[str, Any], spec_meta: dict[str, Any]) -> dict[str, Any]:
        frame_version = _optional_int(frame_meta.get("confirmed_revision"))
        spec_version = None
        if spec_meta.get("confirmed_at"):
            spec_version = _optional_int(spec_meta.get("source_frame_revision"))
        return {
            "frameVersion": frame_version,
            "specVersion": spec_version,
            "splitManifestVersion": None,
        }

    def _packet_kind_for_role(
        self,
        role: ThreadRole,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> str:
        if role == "ask_planning" and self._is_child_activation_node(snapshot, node, node_by_id):
            return "child_activation_context"
        return _ROLE_PACKET_KIND[role]

    def _base_payload(
        self,
        *,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        node_dir: Path,
        workspace_root: str,
        frame_meta: dict[str, Any],
        spec_meta: dict[str, Any],
        role: ThreadRole,
    ) -> dict[str, Any]:
        return {
            "role": role,
            "project": self._project_payload(snapshot, workspace_root),
            "node": self._public_node(node),
            "parentNode": self._public_node(node_by_id.get(str(node.get("parent_id") or ""))),
            "taskContext": self._safe_split_context(snapshot, node, node_by_id),
            "artifactContext": self._artifact_context_payload(
                snapshot=snapshot,
                node=node,
                node_by_id=node_by_id,
                workspace_root=workspace_root,
                node_dir=node_dir,
                frame_meta=frame_meta,
                spec_meta=spec_meta,
            ),
            "frame": {
                "confirmedRevision": _optional_int(frame_meta.get("confirmed_revision")),
                "revision": _optional_int(frame_meta.get("revision")),
                "confirmedAt": _optional_str(frame_meta.get("confirmed_at")),
                "confirmedContent": self._confirmed_frame_content(node_dir, frame_meta),
            },
            "spec": {
                "sourceFrameRevision": _optional_int(spec_meta.get("source_frame_revision")),
                "confirmedAt": _optional_str(spec_meta.get("confirmed_at")),
                "confirmedContent": self._confirmed_spec_content(node_dir, spec_meta),
            },
            "workspaceRoot": workspace_root,
        }

    def _artifact_context_payload(
        self,
        *,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        workspace_root: str,
        node_dir: Path,
        frame_meta: dict[str, Any],
        spec_meta: dict[str, Any],
    ) -> dict[str, Any]:
        ancestors = self._ancestor_nodes(node, node_by_id)
        return {
            "ancestorContext": [
                self._ancestor_artifact_context(
                    snapshot=snapshot,
                    ancestor=ancestor,
                    node_by_id=node_by_id,
                    workspace_root=workspace_root,
                    current_node_id=str(node.get("node_id") or ""),
                )
                for ancestor in ancestors
            ],
            "currentContext": {
                "node": self._public_node(node),
                "frame": self._document_payload(
                    name=planningtree_workspace.FRAME_FILE_NAME,
                    content=self._document_content(node_dir, planningtree_workspace.FRAME_FILE_NAME),
                    meta=frame_meta,
                ),
                "spec": self._document_payload(
                    name=planningtree_workspace.SPEC_FILE_NAME,
                    content=self._document_content(node_dir, planningtree_workspace.SPEC_FILE_NAME),
                    meta=spec_meta,
                ),
            },
        }

    def _ancestor_artifact_context(
        self,
        *,
        snapshot: dict[str, Any],
        ancestor: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        workspace_root: str,
        current_node_id: str,
    ) -> dict[str, Any]:
        node_dir = planningtree_workspace.resolve_node_dir(Path(workspace_root), snapshot, str(ancestor.get("node_id") or ""))
        frame_meta: dict[str, Any] = {}
        clarify: dict[str, Any] | None = None
        frame_content = ""
        if node_dir is not None:
            frame_meta = _load_frame_meta_from_node_dir(node_dir)
            clarify = _load_clarify_from_node_dir(node_dir)
            frame_content = self._document_content(node_dir, planningtree_workspace.FRAME_FILE_NAME)
        return {
            "node": self._public_node(ancestor),
            "frame": self._document_payload(
                name=planningtree_workspace.FRAME_FILE_NAME,
                content=frame_content,
                meta=frame_meta,
            ),
            "clarify": self._clarify_payload(clarify),
            "split": self._split_payload(ancestor, node_by_id, current_node_id),
        }

    @staticmethod
    def _ancestor_nodes(node: dict[str, Any], node_by_id: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        chain: list[dict[str, Any]] = []
        visited: set[str] = set()
        parent_id = str(node.get("parent_id") or "").strip()
        while parent_id and parent_id not in visited:
            visited.add(parent_id)
            parent = node_by_id.get(parent_id)
            if parent is None:
                break
            chain.append(parent)
            parent_id = str(parent.get("parent_id") or "").strip()
        chain.reverse()
        return chain

    @staticmethod
    def _document_content(node_dir: Path, file_name: str) -> str:
        path = node_dir / file_name
        return path.read_text(encoding="utf-8") if path.exists() else ""

    @staticmethod
    def _document_payload(*, name: str, content: str, meta: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": name,
            "content": content,
            "confirmedRevision": _optional_int(meta.get("confirmed_revision")),
            "revision": _optional_int(meta.get("revision")),
            "sourceFrameRevision": _optional_int(meta.get("source_frame_revision")),
            "confirmedAt": _optional_str(meta.get("confirmed_at")),
        }

    @staticmethod
    def _clarify_payload(clarify: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(clarify, dict):
            return {"questions": []}
        questions = clarify.get("questions")
        return {
            "confirmedRevision": _optional_int(clarify.get("confirmed_revision")),
            "confirmedAt": _optional_str(clarify.get("confirmed_at")),
            "questions": copy.deepcopy(questions) if isinstance(questions, list) else [],
        }

    def _split_payload(
        self,
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
        current_node_id: str,
    ) -> dict[str, Any]:
        children = []
        for child_id in node.get("child_ids", []):
            child = node_by_id.get(str(child_id))
            if child is None:
                continue
            public = self._public_node(child)
            if public is None:
                continue
            public["isCurrentPath"] = self._node_contains_descendant(child, current_node_id, node_by_id)
            children.append(public)
        return {"children": children}

    @classmethod
    def _node_contains_descendant(
        cls,
        node: dict[str, Any],
        target_node_id: str,
        node_by_id: dict[str, dict[str, Any]],
    ) -> bool:
        if str(node.get("node_id") or "") == target_node_id:
            return True
        for child_id in node.get("child_ids", []):
            child = node_by_id.get(str(child_id))
            if child is not None and cls._node_contains_descendant(child, target_node_id, node_by_id):
                return True
        return False

    @staticmethod
    def _project_payload(snapshot: dict[str, Any], workspace_root: str) -> dict[str, Any]:
        project = snapshot.get("project") if isinstance(snapshot.get("project"), dict) else {}
        return {
            "id": project.get("id"),
            "name": project.get("name"),
            "rootGoal": project.get("root_goal"),
            "projectPath": workspace_root,
        }

    @staticmethod
    def _public_node(node: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(node, dict):
            return None
        keys = (
            "node_id",
            "parent_id",
            "title",
            "description",
            "status",
            "node_kind",
            "depth",
            "display_order",
            "hierarchical_number",
            "review_node_id",
            "child_ids",
        )
        return {key: copy.deepcopy(node.get(key)) for key in keys if key in node}

    @staticmethod
    def _safe_split_context(
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        try:
            context = build_split_context(snapshot, node, node_by_id)
            return context if isinstance(context, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _confirmed_frame_content(node_dir: Path, frame_meta: dict[str, Any]) -> str:
        if not frame_meta.get("confirmed_at") and not _optional_int(frame_meta.get("confirmed_revision")):
            return ""
        content = str(frame_meta.get("confirmed_content") or "")
        if content:
            return content
        frame_path = node_dir / planningtree_workspace.FRAME_FILE_NAME
        return frame_path.read_text(encoding="utf-8") if frame_path.exists() else ""

    @staticmethod
    def _confirmed_spec_content(node_dir: Path, spec_meta: dict[str, Any]) -> str:
        if not spec_meta.get("confirmed_at"):
            return ""
        spec_path = node_dir / planningtree_workspace.SPEC_FILE_NAME
        return spec_path.read_text(encoding="utf-8") if spec_path.exists() else ""

    def _package_review_payload(
        self,
        project_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        review_node = node if node.get("node_kind") == "review" else None
        if review_node is None:
            review_node_id = _optional_str(node.get("review_node_id"))
            if review_node_id:
                review_node = node_by_id.get(review_node_id)
        parent = None
        if review_node is not None:
            parent = node_by_id.get(str(review_node.get("parent_id") or ""))
        if parent is None:
            parent = node
        review_state = None
        if review_node is not None:
            review_state = self._storage.workflow_domain_store.read_review(
                project_id,
                str(review_node.get("node_id") or ""),
            )
        children = [
            self._public_node(node_by_id.get(str(child_id)))
            for child_id in (parent.get("child_ids") or [])
            if self._public_node(node_by_id.get(str(child_id))) is not None
        ]
        return {
            "parentNode": self._public_node(parent),
            "reviewNode": self._public_node(review_node),
            "children": children,
            "childRollup": copy.deepcopy(review_state.get("rollup")) if isinstance(review_state, dict) else None,
            "checkpoints": copy.deepcopy(review_state.get("checkpoints")) if isinstance(review_state, dict) else [],
            "pendingSiblingManifest": (
                copy.deepcopy(review_state.get("pending_siblings")) if isinstance(review_state, dict) else []
            ),
            "reviewState": copy.deepcopy(review_state),
        }

    def _is_child_activation_node(
        self,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        node_by_id: dict[str, dict[str, Any]],
    ) -> bool:
        del snapshot
        parent = node_by_id.get(str(node.get("parent_id") or ""))
        if parent is None:
            return False
        review_node_id = _optional_str(parent.get("review_node_id"))
        return review_node_id is not None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value).strip()
        return int(text) if text else None
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
