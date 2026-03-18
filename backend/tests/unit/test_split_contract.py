from __future__ import annotations

import pytest

from backend.errors.app_errors import InvalidRequest
from backend.split_contract import (
    CANONICAL_SPLIT_MODE_REGISTRY,
    TEMPORARY_LEGACY_ROUTE_BRIDGE,
    parse_route_split_mode_or_raise,
)


def test_canonical_split_mode_registry_contains_all_supported_modes() -> None:
    assert set(CANONICAL_SPLIT_MODE_REGISTRY) == {
        "workflow",
        "simplify_workflow",
        "phase_breakdown",
        "agent_breakdown",
    }


@pytest.mark.parametrize(
    ("mode", "min_items", "max_items"),
    [
        ("workflow", 3, 7),
        ("simplify_workflow", 2, 5),
        ("phase_breakdown", 3, 6),
        ("agent_breakdown", 4, 7),
    ],
)
def test_canonical_split_mode_registry_preserves_metadata(
    mode: str,
    min_items: int,
    max_items: int,
) -> None:
    spec = CANONICAL_SPLIT_MODE_REGISTRY[mode]  # type: ignore[index]

    assert spec["id"] == mode
    assert spec["output_family"] == "flat_subtasks_v1"
    assert spec["min_items"] == min_items
    assert spec["max_items"] == max_items
    assert spec["visible_in_ui"] is True
    assert spec["creation_enabled"] is True


@pytest.mark.parametrize("mode", list(CANONICAL_SPLIT_MODE_REGISTRY))
def test_parse_route_split_mode_accepts_canonical_modes(mode: str) -> None:
    assert parse_route_split_mode_or_raise(mode) == mode


@pytest.mark.parametrize("mode", sorted(TEMPORARY_LEGACY_ROUTE_BRIDGE))
def test_parse_route_split_mode_accepts_temporary_legacy_bridge_modes(mode: str) -> None:
    assert parse_route_split_mode_or_raise(mode) == mode


def test_parse_route_split_mode_rejects_unknown_mode() -> None:
    with pytest.raises(InvalidRequest, match="Unsupported split mode."):
        parse_route_split_mode_or_raise("bad-mode")
