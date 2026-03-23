from __future__ import annotations

from backend.ai.split_prompt_builder import (
    build_split_attempt_prompt,
    build_split_base_instructions,
)


def test_split_base_instructions_mentions_task_frame_constraints() -> None:
    instructions = build_split_base_instructions()
    lowered = instructions.lower()
    assert "task frame" in lowered
    assert "constraints" in lowered


def test_build_split_prompt_uses_task_frame_not_technical_spec() -> None:
    prompt = build_split_attempt_prompt(
        "workflow",
        {
            "current_node_prompt": "Build the marketing site entry flow",
            "root_prompt": "Ship the first public-facing website",
            "parent_chain_prompts": ["Website MVP: Demo-ready first release"],
            "prior_node_summaries_compact": [],
            "frame_content": (
                "# Task Title\n"
                "Core Site Entry\n\n"
                "# Task-Shaping Fields\n"
                "- frontend stack: React + Tailwind\n"
            ),
        },
    )

    assert "Task frame:" in prompt
    assert "React + Tailwind" in prompt
    assert "Technical spec:" not in prompt
    assert "reflect those choices concretely" in prompt

