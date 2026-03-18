from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.split_contract import CANONICAL_SPLIT_MODE_REGISTRY, CanonicalSplitModeId, FlatSubtaskItem, FlatSubtaskPayload


def build_canonical_split_fallback(
    mode: CanonicalSplitModeId,
    task_context: dict[str, Any],
) -> FlatSubtaskPayload:
    builder = _FALLBACK_BUILDERS[mode]
    subtasks = builder(task_context)
    spec = CANONICAL_SPLIT_MODE_REGISTRY[mode]
    if not spec["min_items"] <= len(subtasks) <= spec["max_items"]:
        raise ValueError(
            f"Canonical fallback for {mode} produced {len(subtasks)} items; "
            f"expected {spec['min_items']} to {spec['max_items']}."
        )
    return {"subtasks": subtasks}


def _build_workflow_fallback(task_context: dict[str, Any]) -> list[FlatSubtaskItem]:
    subject = _task_subject(task_context)
    return [
        _subtask(
            "S1",
            "Define the working flow",
            f"Identify the smallest end-to-end workflow for {subject} and capture the setup needed to start execution.",
            "The first step should establish the sequence that every later task will follow.",
        ),
        _subtask(
            "S2",
            "Build the core flow",
            f"Implement the central execution path for {subject} from first input to successful output.",
            "Once the workflow is clear, the highest-value progress is making the main path work.",
        ),
        _subtask(
            "S3",
            "Verify and finish the flow",
            f"Test the completed workflow for {subject}, close integration gaps, and leave it ready for dependable handoff.",
            "Validation belongs after the main path exists so fixes stay grounded in a real working flow.",
        ),
    ]


def _build_simplify_workflow_fallback(task_context: dict[str, Any]) -> list[FlatSubtaskItem]:
    subject = _task_subject(task_context)
    return [
        _subtask(
            "S1",
            "Ship the minimum valid path",
            f"Create the smallest working version of {subject} that still achieves the intended outcome.",
            "A reduced core path lowers risk and reveals what is truly required.",
        ),
        _subtask(
            "S2",
            "Add the next essential layer",
            f"Reintroduce the most important missing coverage, safeguards, or polish needed to make {subject} dependable.",
            "Only after the core path works should the next layer be added back deliberately.",
        ),
    ]


def _build_phase_breakdown_fallback(task_context: dict[str, Any]) -> list[FlatSubtaskItem]:
    subject = _task_subject(task_context)
    return [
        _subtask(
            "S1",
            "Phase 1: Lowest-risk scaffold",
            f"Set up the safest, smallest-surface implementation slice for {subject} so later work has a stable base.",
            "Starting with the lowest blast radius keeps the first phase reversible and easier to validate.",
        ),
        _subtask(
            "S2",
            "Phase 2: Deliver the main capability",
            f"Extend the scaffold into the main user-visible behavior required for {subject}.",
            "Once the base exists, the next phase should convert it into a working capability.",
        ),
        _subtask(
            "S3",
            "Phase 3: Harden and complete",
            f"Add integration checks, edge-case handling, and finishing work so {subject} is ready for dependable use.",
            "Hardening belongs after the main path exists, when real integration points are known.",
        ),
    ]


def _build_agent_breakdown_fallback(task_context: dict[str, Any]) -> list[FlatSubtaskItem]:
    subject = _task_subject(task_context)
    return [
        _subtask(
            "S1",
            "Stabilize dependencies and inputs",
            f"Clarify interfaces, dependencies, and required inputs around {subject} before deeper changes begin.",
            "Conservative splits start by reducing ambiguity at the boundaries.",
        ),
        _subtask(
            "S2",
            "Implement the core invariant-preserving change",
            f"Make the central change for {subject} while preserving the key invariants that surrounding work depends on.",
            "The core change should happen only after its boundaries and invariants are explicit.",
        ),
        _subtask(
            "S3",
            "Handle migration and integration edges",
            f"Adapt downstream callers, data movement, or integration points so {subject} works across existing boundaries.",
            "Integration work is safer after the main change exists in a controlled form.",
        ),
        _subtask(
            "S4",
            "Clean up and verify",
            f"Remove temporary scaffolding, close follow-up gaps, and verify {subject} behaves correctly end to end.",
            "Cleanup and verification should come last, after the integration edges settle.",
        ),
    ]


_FALLBACK_BUILDERS: dict[
    CanonicalSplitModeId,
    Callable[[dict[str, Any]], list[FlatSubtaskItem]],
] = {
    "workflow": _build_workflow_fallback,
    "simplify_workflow": _build_simplify_workflow_fallback,
    "phase_breakdown": _build_phase_breakdown_fallback,
    "agent_breakdown": _build_agent_breakdown_fallback,
}


def _subtask(item_id: str, title: str, objective: str, why_now: str) -> FlatSubtaskItem:
    return {
        "id": item_id,
        "title": title,
        "objective": objective,
        "why_now": why_now,
    }


def _task_subject(task_context: dict[str, Any]) -> str:
    current_prompt = _normalize_text(task_context.get("current_node_prompt"))
    root_prompt = _normalize_text(task_context.get("root_prompt"))
    return current_prompt or root_prompt or "the current task"


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).strip()
