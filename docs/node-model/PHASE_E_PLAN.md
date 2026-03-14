# Phase E: AI Spec Generation for Nodes

Last updated: 2026-03-12

## Goal

Add explicit AI-assisted spec generation on top of the Phase D lifecycle so a node in spec review can synthesize a full `spec.md` draft from canonical node context.

## Delivered

### Prompting and response handling

- added `backend/ai/spec_prompt_builder.py`
- spec generation asks Codex for exactly one JSON object with:
  - `business_contract`
  - `technical_contract`
  - `delivery_acceptance`
  - `assumptions`
- invalid model output gets one retry with hidden validation feedback
- malformed output after retry returns typed `502 spec_generation_invalid_response`

### Service and route

- added `SpecGenerationService`
- added `POST /projects/{pid}/nodes/{nid}/generate-spec`
- generation is synchronous request/response
- generation uses canonical context only:
  - project root goal
  - parent chain task summaries
  - current `task.md`
  - current `briefing.md`
  - current `spec.md`

### Persistence and lifecycle

- successful generation replaces the full `spec.md`
- successful generation sets `state.yaml.spec_generated = true`
- added `state.yaml.spec_generation_status` with `idle | generating | failed`
- if generation runs from `ready_for_execution`, the regenerated spec uses the normal spec-edit lifecycle path and steps the node back to `spec_review`
- failed generation leaves the existing `spec.md` unchanged
- startup recovery converts stranded `spec_generation_status=generating` states to `failed`

## Verification

- `python -m pytest backend/tests/unit/test_spec_prompt_builder.py -q`
- `python -m pytest backend/tests/unit/test_spec_generation_service.py -q`
- `python -m pytest backend/tests/integration/test_spec_generation_api.py -q`
- `python -m pytest backend/tests -q`

## Follow-up

Frontend trigger UI remains deferred. Existing manual spec save/confirm flows continue to work without changes and can adopt the new route in a later phase.
