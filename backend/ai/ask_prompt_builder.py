from __future__ import annotations

from typing import Any


def build_ask_base_instructions() -> str:
    return (
        "You are the PlanningTree Ask assistant for a specific planning node.\n\n"
        "Your role is to answer questions about this node's plan, clarify scope, "
        "identify risks, surface dependencies, and help the user explore alternatives.\n\n"
        "You are operating inside a per-node ask thread that inherits planning context "
        "from the node's planning thread.\n\n"
        "Focus on explanation and analysis. Do not claim to have changed the plan or "
        "the workspace unless the user explicitly asks for execution in a different flow.\n\n"
        "When the conversation surfaces a materially new insight, risk, dependency, scope "
        "clarification, or decision that should be preserved in planning context, call "
        "emit_render_data with kind='delta_context_suggestion'. The payload must map "
        "directly to the tool fields: payload.summary must be a short, non-empty one-line "
        "summary, and payload.context_text must be the full, non-empty planning context "
        "to preserve. Never leave summary or context_text empty. If you cannot provide "
        "both fields with concrete content, do not call emit_render_data. Format the "
        "tool call like this: emit_render_data(kind='delta_context_suggestion', "
        "payload={'summary': 'Short summary here', 'context_text': 'Full planning "
        "context here.'}). Do not emit this tool call for every answer."
    )


def ask_thread_render_tool() -> dict[str, Any]:
    return {
        "name": "emit_render_data",
        "description": "Suggest capturing a new planning insight from this conversation.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["delta_context_suggestion"]},
                "payload": {
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "context_text": {"type": "string"},
                    },
                    "required": ["summary", "context_text"],
                },
            },
            "required": ["kind", "payload"],
        },
    }
