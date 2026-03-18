# Phase 2 Progress

Last updated: 2026-03-17

## Status

- completed

## Entries

### 2026-03-17

- Added `backend/ai/legacy_split_prompt_builder.py` and moved the existing `walking_skeleton` and `slice` prompt-schema behavior into explicitly legacy-prefixed helpers.
- Refactored `backend/ai/split_prompt_builder.py` into a canonical-only prompt and schema module for `workflow`, `simplify_workflow`, `phase_breakdown`, and `agent_breakdown`.
- Added the shared canonical `flat_subtasks_v1` schema example, parser, validator, payload issue helper, and hidden retry feedback contract.
- Rewired `backend/services/thread_service.py` to keep using legacy planning base instructions for the pre-cutover runtime.
- Rewired `backend/services/split_service.py` to keep using legacy split prompt, validation, issue, and retry helpers for `walking_skeleton` and `slice`.
- Replaced old prompt-builder tests with canonical coverage and added a separate legacy bridge regression test module.
