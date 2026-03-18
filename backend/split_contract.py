from __future__ import annotations

from typing import Final, Literal, TypedDict, cast

from backend.errors.app_errors import InvalidRequest

CanonicalSplitModeId = Literal[
    "workflow",
    "simplify_workflow",
    "phase_breakdown",
    "agent_breakdown",
]
SplitOutputFamily = Literal["flat_subtasks_v1"]
TemporaryLegacyRouteModeId = Literal["walking_skeleton", "slice"]
RouteAcceptedSplitMode = Literal[
    "workflow",
    "simplify_workflow",
    "phase_breakdown",
    "agent_breakdown",
    "walking_skeleton",
    "slice",
]


class SplitModeSpec(TypedDict):
    id: CanonicalSplitModeId
    label: str
    description: str
    output_family: SplitOutputFamily
    min_items: int
    max_items: int
    visible_in_ui: bool
    creation_enabled: bool


CANONICAL_SPLIT_MODE_REGISTRY: dict[CanonicalSplitModeId, SplitModeSpec] = {
    "workflow": {
        "id": "workflow",
        "label": "Workflow",
        "description": "Workflow-first sequential split.",
        "output_family": "flat_subtasks_v1",
        "min_items": 3,
        "max_items": 7,
        "visible_in_ui": True,
        "creation_enabled": True,
    },
    "simplify_workflow": {
        "id": "simplify_workflow",
        "label": "Simplify Workflow",
        "description": "Minimum valid core workflow first, then additive reintroduction.",
        "output_family": "flat_subtasks_v1",
        "min_items": 2,
        "max_items": 5,
        "visible_in_ui": True,
        "creation_enabled": True,
    },
    "phase_breakdown": {
        "id": "phase_breakdown",
        "label": "Phase Breakdown",
        "description": "Phase-based sequential delivery split.",
        "output_family": "flat_subtasks_v1",
        "min_items": 3,
        "max_items": 6,
        "visible_in_ui": True,
        "creation_enabled": True,
    },
    "agent_breakdown": {
        "id": "agent_breakdown",
        "label": "Agent Breakdown",
        "description": "Conservative non-workflow split when other shapes are a weak fit.",
        "output_family": "flat_subtasks_v1",
        "min_items": 4,
        "max_items": 7,
        "visible_in_ui": True,
        "creation_enabled": True,
    },
}

TEMPORARY_LEGACY_ROUTE_BRIDGE: Final[frozenset[str]] = frozenset({"walking_skeleton", "slice"})
_ACCEPTED_ROUTE_SPLIT_MODES: Final[frozenset[str]] = frozenset(
    {*CANONICAL_SPLIT_MODE_REGISTRY.keys(), *TEMPORARY_LEGACY_ROUTE_BRIDGE}
)


def parse_route_split_mode_or_raise(raw: str) -> RouteAcceptedSplitMode:
    normalized = raw.strip()
    if normalized in _ACCEPTED_ROUTE_SPLIT_MODES:
        return cast(RouteAcceptedSplitMode, normalized)
    raise InvalidRequest("Unsupported split mode.")
