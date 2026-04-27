from __future__ import annotations

import hashlib
import json
import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ContextPacketKind = Literal[
    "ask_planning_context",
    "child_activation_context",
    "execution_context",
    "audit_context",
    "package_review_context",
    "context_update",
]


class PlanningTreeContextPacket(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_version: int = Field(default=1, alias="schemaVersion")
    kind: ContextPacketKind
    project_id: str = Field(alias="projectId")
    node_id: str = Field(alias="nodeId")
    payload: dict[str, Any] = Field(default_factory=dict)
    source_versions: dict[str, Any] = Field(default_factory=dict, alias="sourceVersions")

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(by_alias=True, mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )

    def packet_hash(self) -> str:
        canonical = self.canonical_json()
        return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

    def render_model_visible_message(self) -> str:
        body = self.canonical_json()
        return (
            f'<planning_tree_context kind="{self.kind}" schema_version="{self.schema_version}">\n'
            f"{body}\n"
            "</planning_tree_context>"
        )

    def ui_context_payload(self) -> dict[str, Any]:
        if self.kind == "context_update":
            next_context = self.payload.get("nextContext")
            if isinstance(next_context, dict):
                next_payload = next_context.get("payload")
                if isinstance(next_payload, dict):
                    return copy.deepcopy(next_payload)
        return copy.deepcopy(self.payload)
