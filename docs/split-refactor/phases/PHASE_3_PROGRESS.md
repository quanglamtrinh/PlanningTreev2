# Phase 3 Progress

Last updated: 2026-03-17

## Status

- completed

## Entries

### 2026-03-17

- Extended `backend/split_contract.py` with service-facing split mode and output-family helpers plus typed canonical flat-subtask payload aliases.
- Added `split_runtime_bundle_for_mode(...)` so `SplitService` now selects prompt, validation, issue, and hidden retry helpers consistently by mode.
- Refactored `backend/services/split_service.py` so canonical payload materialization now branches by `output_family` and uses a shared `flat_subtasks_v1` child-creation path.
- Added stable canonical `split_metadata.output_family`, normalized `materialized` metadata, and debug-scoped raw payload capture for flat-family splits.
- Locked canonical fallback behind an explicit service-level guard until Phase 4.
- Added canonical service tests while preserving legacy bridge and route-guard coverage.
