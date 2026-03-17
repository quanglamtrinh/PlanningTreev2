from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.services.node_task_fields import load_task_prompt_fields
from backend.storage.storage import Storage


class ConversationContextBuilder:
    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def build_execution_request(
        self,
        *,
        project_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        state: dict[str, Any],
        user_message: str,
    ) -> dict[str, Any]:
        workspace_root = self._workspace_root_from_snapshot(snapshot)
        fields = load_task_prompt_fields(
            self._storage.node_store,
            project_id,
            str(node.get("node_id") or ""),
        )
        context = {
            "project_name": str(snapshot.get("project", {}).get("name") or ""),
            "project_root_goal": str(snapshot.get("project", {}).get("root_goal") or ""),
            "workspace_root": workspace_root,
            "thread_type": "execution",
            "runtime_mode": "execute",
            "node": {
                "node_id": str(node.get("node_id") or ""),
                "title": fields["title"],
                "description": fields["description"],
                "hierarchical_number": str(node.get("hierarchical_number") or ""),
                "status": str(node.get("status") or ""),
                "phase": str(state.get("phase") or node.get("phase") or ""),
            },
            "state": {
                "run_status": str(state.get("run_status") or ""),
                "plan_status": str(state.get("plan_status") or ""),
                "brief_version": int(state.get("brief_version", 0) or 0),
                "spec_version": int(state.get("active_spec_version", 0) or 0),
            },
            "task": self._storage.node_store.load_task(project_id, str(node.get("node_id") or "")),
            "brief": self._storage.node_store.load_brief(project_id, str(node.get("node_id") or "")),
            "spec": self._storage.node_store.load_spec(project_id, str(node.get("node_id") or "")),
            "plan": self._storage.node_store.load_plan(project_id, str(node.get("node_id") or "")),
        }
        prompt = "\n\n".join(
            [
                "You are the PlanningTree node execution assistant.",
                "Work only from the current node context and workspace settings below.",
                "Use the Spec as the governing contract. Use the Brief and Plan as supporting context only.",
                "Do not mention hidden metadata unless the user asks for it.",
                "Hidden context:",
                json.dumps(context, ensure_ascii=True, indent=2),
                "User message:",
                str(user_message),
            ]
        )
        return {
            "prompt": prompt,
            "cwd": workspace_root,
            "writable_roots": [workspace_root],
            "timeout_sec": 120,
        }

    def build_execution_action_request(
        self,
        *,
        project_id: str,
        snapshot: dict[str, Any],
        node: dict[str, Any],
        state: dict[str, Any],
        action: str,
        target_message: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        workspace_root = self._workspace_root_from_snapshot(snapshot)
        fields = load_task_prompt_fields(
            self._storage.node_store,
            project_id,
            str(node.get("node_id") or ""),
        )
        context = {
            "project_name": str(snapshot.get("project", {}).get("name") or ""),
            "project_root_goal": str(snapshot.get("project", {}).get("root_goal") or ""),
            "workspace_root": workspace_root,
            "thread_type": "execution",
            "runtime_mode": "execute",
            "action": action,
            "node": {
                "node_id": str(node.get("node_id") or ""),
                "title": fields["title"],
                "description": fields["description"],
                "hierarchical_number": str(node.get("hierarchical_number") or ""),
                "status": str(node.get("status") or ""),
                "phase": str(state.get("phase") or node.get("phase") or ""),
            },
            "state": {
                "run_status": str(state.get("run_status") or ""),
                "plan_status": str(state.get("plan_status") or ""),
                "brief_version": int(state.get("brief_version", 0) or 0),
                "spec_version": int(state.get("active_spec_version", 0) or 0),
            },
            "task": self._storage.node_store.load_task(project_id, str(node.get("node_id") or "")),
            "brief": self._storage.node_store.load_brief(project_id, str(node.get("node_id") or "")),
            "spec": self._storage.node_store.load_spec(project_id, str(node.get("node_id") or "")),
            "plan": self._storage.node_store.load_plan(project_id, str(node.get("node_id") or "")),
            "target_message": target_message or None,
        }
        action_instruction = {
            "continue": "Continue the current execution from the targeted completed assistant result without replacing prior output.",
            "retry": "Retry after the targeted non-success assistant result. Start a new branch and preserve the failed result for replay.",
            "regenerate": "Regenerate the targeted completed assistant result. Create a superseding branch and preserve the replaced result for replay.",
        }.get(action, f"Perform the requested execution action: {action}.")
        prompt = "\n\n".join(
            [
                "You are the PlanningTree node execution assistant.",
                "Work only from the current node context and workspace settings below.",
                "Use the Spec as the governing contract. Use the Brief and Plan as supporting context only.",
                "Do not mention hidden metadata unless the user asks for it.",
                action_instruction,
                "Hidden context:",
                json.dumps(context, ensure_ascii=True, indent=2),
            ]
        )
        return {
            "prompt": prompt,
            "cwd": workspace_root,
            "writable_roots": [workspace_root],
            "timeout_sec": 120,
        }

    def _workspace_root_from_snapshot(self, snapshot: dict[str, Any]) -> str:
        project = snapshot.get("project", {})
        if not isinstance(project, dict):
            raise ValueError("project workspace_root is required for conversation context")
        raw_workspace_root = str(project.get("project_workspace_root") or "").strip()
        if not raw_workspace_root:
            raise ValueError("project workspace_root is required for conversation context")
        workspace_path = Path(raw_workspace_root).expanduser().resolve()
        if not workspace_path.exists() or not workspace_path.is_dir():
            raise ValueError(f"project workspace_root is invalid: {workspace_path}")
        return str(workspace_path)
