# Phase 1 Progress

Last updated: 2026-03-17

## Status

- completed

## Entries

### 2026-03-17

- Added `backend/split_contract.py` with the canonical mode registry and explicit route parser.
- Updated `backend/routes/split.py` to close the route boundary without switching bad-mode behavior to framework-default `422`.
- Landed the temporary route bridge for `walking_skeleton` and `slice` so the current split runtime still works during the pre-cutover phases.
- Added unit coverage for the registry and parser.
- Added integration coverage proving canonical modes are guarded before `split_service.split_node(...)` is invoked.
