# Phase 5 Validation

Last updated: 2026-03-17

## Validation Commands Run

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests/unit/test_split_contract.py backend/tests/integration/test_split_api.py -q
Set-Location frontend; npx vitest run tests/unit/GraphWorkspace.test.tsx tests/unit/TreeGraph.test.tsx tests/unit/PlanningPanel.test.tsx tests/unit/project-store.test.ts tests/unit/ConversationSurface.test.tsx tests/unit/normalizeSplitPayload.test.ts
npm --prefix frontend run typecheck
```

## Test Coverage Touched

- Public split route acceptance for canonical modes and rejection for legacy or invalid modes.
- GraphNode split menu wiring through TreeGraph and GraphWorkspace canonical create paths.
- Project store canonical split action handling plus legacy planning-mode read tolerance.
- Planning panel removal of duplicate split affordances.
- Canonical flat split-result rendering and legacy split payload read compatibility.
- Frontend type-check coverage for canonical mode model changes.

## Manual Checks Performed

- Confirmed the public `/split` route no longer rejects canonical modes with the Phase 4 guard.
- Confirmed legacy `walking_skeleton` and `slice` are no longer valid public route inputs.
- Confirmed GraphNode is the only exposed split entrypoint in the frontend.
- Confirmed canonical flat subtasks render in conversation surfaces while legacy payloads remain readable.

## Failures, Warnings, Or Residual Risks

- Targeted frontend tests still emit pre-existing React act warnings in some workspace and conversation tests.
- Conversation rendering tests still surface an existing React key warning inside the tool-call block renderer.
- Full repo validation was not run.

## Final Validation Outcome

- Phase 5 public route flip and frontend canonical split migration validated with targeted backend tests, targeted frontend tests, and frontend type-checking.
