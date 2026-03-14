from __future__ import annotations

import json
from typing import Any

from backend.ai.spec_prompt_builder import spec_generation_schema_example


def build_spec_patch_prompt(
    context: dict[str, Any],
    retry_feedback: str | None = None,
) -> str:
    prompt_parts = [
        "You are updating a PlanningTree Spec after a planning session with the user.",
        (
            "Return a complete replacement Spec object using the existing Spec as the base. "
            "Preserve unchanged content whenever possible."
        ),
        (
            "Only incorporate information that is supported by the plan-session transcript and resolved user answers. "
            "Do not introduce unrelated scope or constraints."
        ),
        (
            "Return exactly one JSON object. Do not use markdown fences. "
            "Do not include any explanation before or after the JSON."
        ),
        (
            "Use exactly these top-level object keys: "
            "mission, scope, constraints, autonomy, verification, execution_controls, assumptions."
        ),
        (
            "Inside each section, use only scalar string fields and array-of-string list fields. "
            "Do not return markdown-encoded strings."
        ),
        "Canonical spec patch context:",
        json.dumps(context, indent=2, ensure_ascii=True),
        "Required JSON shape example:",
        json.dumps(spec_generation_schema_example(), indent=2, ensure_ascii=True),
    ]

    if retry_feedback:
        prompt_parts.extend(
            [
                "The previous attempt was invalid.",
                retry_feedback,
                "Fix the issues and return a valid JSON object with the exact required keys and field types.",
            ]
        )

    return "\n\n".join(prompt_parts)
