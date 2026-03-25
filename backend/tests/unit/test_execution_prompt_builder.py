from __future__ import annotations

from backend.ai.execution_prompt_builder import (
    build_execution_base_instructions,
    build_execution_prompt,
)


def test_execution_base_instructions_require_progress_commentary() -> None:
    prompt = build_execution_base_instructions()

    assert "emit brief progress commentary" in prompt
    assert "Before each meaningful inspection step" in prompt
    assert "After each meaningful result or verification step" in prompt


def test_execution_prompt_requires_streaming_progress_updates() -> None:
    prompt = build_execution_prompt(
        spec_content="# Spec\nShip it\n",
        frame_content="# Frame\nBuild it\n",
        task_context={
            "root_prompt": "Snake game",
            "current_node_prompt": "Set up the playable Snake board",
            "node_id": "node-1",
            "tree_depth": 1,
            "parent_chain_prompts": ["Snake game"],
            "prior_node_summaries_compact": [],
            "existing_children_count": 0,
        },
    )

    assert "While working, stream short progress updates" in prompt
    assert "When complete, provide a brief summary" in prompt
