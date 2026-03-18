# Phase 2 Plan: Canonical Prompt Builder And Shared Flat Contract

Last updated: 2026-03-17

## Phase Goal

- Turn `backend/ai/split_prompt_builder.py` into the canonical prompt and schema module for the 4 new split modes.
- Extract the old `walking_skeleton` and `slice` prompt-schema behavior into a temporary legacy bridge so the Phase 1 route bridge keeps the current runtime functional.

## In-Scope Changes

- Add `backend/ai/legacy_split_prompt_builder.py` for legacy planning instructions, split user messages, payload validation, payload issues, generation parsing, and hidden retry feedback.
- Keep `planning_render_tool()` shared and mode-neutral in `backend/ai/split_prompt_builder.py`.
- Refactor `backend/ai/split_prompt_builder.py` to canonical-only APIs using `CanonicalSplitModeId`.
- Add a shared `flat_subtasks_v1` schema example, parser, validator, payload issue helper, generation prompt builder, and hidden retry feedback for the 4 canonical modes.
- Repoint `ThreadService` and `SplitService` imports so the current old-mode runtime uses the temporary legacy bridge.
- Add targeted unit and integration coverage for the canonical contract and the legacy bridge regression path.

## Out-Of-Scope Boundaries

- Making canonical modes executable.
- `SplitService` output-family materialization refactor.
- Deterministic fallback migration.
- Frontend registry or UI exposure changes.
- Removal of the Phase 1 route bridge.

## Implementation Tasks

- Create `backend/ai/legacy_split_prompt_builder.py` by extracting the current old-mode prompt logic with explicitly legacy-prefixed APIs.
- Keep `planning_render_tool()` in `backend/ai/split_prompt_builder.py` and make the rest of that module canonical-only.
- Drive canonical count limits and output-family assumptions from `CANONICAL_SPLIT_MODE_REGISTRY`.
- Enforce the shared flat schema:
  - top-level key exactly `subtasks`
  - item keys exactly `id`, `title`, `objective`, `why_now`
  - no extra keys
  - non-blank normalized string values
  - unique `id` values
  - authoritative list order
- Ensure canonical parsing does not alias legacy keys like `prompt`, `risk_reason`, or `what_unblocks`.
- Rewire `ThreadService` to use legacy planning base instructions and `SplitService` to use legacy split message, validation, issues, and retry helpers.
- Add tests proving:
  - canonical prompts and planning instructions cover only the 4 new modes
  - canonical parser and validator enforce the shared flat contract
  - hidden retry feedback uses the same canonical schema example
  - legacy helper behavior for `walking_skeleton` and `slice` still works after extraction
  - existing split API coverage remains green through the temporary bridge

## Acceptance Checks

- `backend/ai/split_prompt_builder.py` exposes only canonical prompt-schema APIs for the 4 new modes.
- `backend/ai/legacy_split_prompt_builder.py` preserves the old-mode prompt behavior needed by the temporary bridge.
- Canonical parsing rejects legacy payload shapes instead of remapping them.
- Existing `walking_skeleton` and `slice` runtime behavior still works through the legacy bridge and the Phase 1 route guard.

## Open Phase-Local Risks

- Import rewiring must not accidentally move runtime code onto the canonical prompt path before Phases 3 and 4 land.
- Canonical prompt/schema helpers are intentionally ahead of service materialization, so new modes remain non-executable until later phases.
