from __future__ import annotations

import hashlib
import json
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

    def packet_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(by_alias=True, mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"

    def render_model_visible_message(self) -> str:
        body = json.dumps(self.model_dump(by_alias=True, mode="json"), ensure_ascii=True, sort_keys=True)
        return (
            f'<planning_tree_context kind="{self.kind}" schema_version="{self.schema_version}">\n'
            f"{body}\n"
            "</planning_tree_context>"
        )

