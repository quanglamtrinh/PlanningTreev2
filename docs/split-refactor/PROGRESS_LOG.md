# Split Refactor Progress Log

Last updated: 2026-03-17

## Phase Status

| Phase | Status | Notes |
| --- | --- | --- |
| Phase 1 | completed | Registry and route guard landed with a temporary legacy route bridge |
| Phase 2 | completed | Canonical prompt builder landed with a strict flat-schema contract and a separate legacy bridge module |
| Phase 3 | completed | SplitService now materializes canonical modes through one flat-family path while keeping route-level canonical guard intact |
| Phase 4 | completed | Canonical deterministic fallback landed at the backend service layer while route behavior stayed unchanged |
| Phase 5 | completed | Public `/split` now accepts canonical modes and the frontend create path is canonical-only through GraphNode |
| Phase 6 | completed | Legacy graph-side split placeholders removed and current docs aligned with GraphNode as the only live split surface |
| Phase 7 | pending | Cutover cleanup not started |
| Phase 8 | pending | Tests and docs stabilization not started |

## Entries

### 2026-03-17

- Created the `docs/split-refactor/` scaffold.
- Added `MASTER_PLAN.md`, `DECISION_LOG.md`, `IMPLEMENTATION_CHECKLIST.md`, `PROGRESS_LOG.md`, `OPEN_ISSUES.md`, and `phases/README.md`.
- Locked the effort as a backend-first hard cutover to the 4 canonical modes and the shared `flat_subtasks_v1` output family.
- Preserved the rule that phase-specific docs must only be created when a phase actually starts.
- Started and completed Phase 1 with a canonical split registry, closed route parsing, and a temporary legacy route bridge for `walking_skeleton` and `slice`.
- Added targeted tests proving bad modes still return `400 invalid_request` and canonical new modes are guarded before the service is called.
- Started and completed Phase 2 by separating canonical and legacy prompt-schema paths.
- Added `backend/ai/legacy_split_prompt_builder.py` for the temporary old-mode bridge and made `backend/ai/split_prompt_builder.py` canonical-only for the 4 new modes.
- Rewired `ThreadService` and `SplitService` imports so the existing old-mode runtime stays on the legacy bridge.
- Added canonical prompt-builder coverage, legacy bridge regression tests, and targeted validation showing the bridge remains intact while the new flat contract is enforced in the canonical module.
- Started and completed Phase 3 by making `SplitService` output-family-driven for canonical payload materialization.
- Added service-facing split contract helpers, a mode-to-runtime bundle dispatch helper, and a shared canonical flat-subtask materializer.
- Preserved the Phase 1 route guard and the legacy bridge while making canonical service execution fail closed and explicit if it reaches fallback before Phase 4.
- Added canonical service tests for flat-family materialization, revision handling, and failure behavior while keeping legacy bridge and API guard coverage green.
- Started and completed Phase 4 by replacing the canonical fallback guard with deterministic canonical fallback for all 4 new modes.
- Added a dedicated canonical fallback module, revalidated fallback payloads before materialization, and kept canonical execution on the same shared `flat_subtasks_v1` contract and apply path.
- Preserved the public route guard and the legacy bridge while making canonical split execution backend-complete and adding targeted fallback coverage.
- Started and completed Phase 5 by opening the public `/split` route for the 4 canonical modes and removing legacy modes from the public split contract.
- Added frontend canonical split typing, a graph split registry, and generic canonical split wiring through GraphNode, TreeGraph, GraphWorkspace, the API client, and the project store.
- Removed PlanningConversationPanel split affordances so GraphNode is now the only exposed split entrypoint in the primary UI path.
- Added shared split-payload normalization so canonical flat subtasks render correctly while legacy split payloads remain readable during the transition window.
- Added targeted backend route tests, frontend graph/store/render tests, and frontend typecheck coverage for the public cutover.
- Started and completed Phase 6 by deleting the unused legacy graph action panel component and leaving GraphNode as the only live split surface.
- Updated current docs so split creation is described through GraphNode, GraphWorkspace, `routes/split.py`, and the asynchronous planning-completion flow.
- Added Phase 6 tracking docs plus targeted validation covering graph-menu tests, planning-host split-entrypoint proof, frontend typecheck, and repo-search acceptance for stale current-doc references.
