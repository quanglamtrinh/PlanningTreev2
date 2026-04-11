# Phase 5 Frontend Regression Notes

Date: 2026-04-10  
Owner: FE Conversion Track

## Goal

Cut over active frontend workflow control-plane to V3 without user-facing behavior regressions on `/chat-v2`.

## Regression Surface Checked

- `BreadcrumbChatViewV2` tab routing and thread loading for ask/execution/audit.
- Workflow action gating and action-to-route transitions:
  - execution: review-in-audit, mark-done
  - audit: improve-in-execution, mark-done
- `NodeDocumentEditor` spec confirm-and-finish flow (workflow finish-task mutation path).
- Workflow event bridge reconnect and invalidate behavior.
- `MessagesV3` plan-ready card gating semantics using canonical `threadRole`.

## Parity Outcomes

1. Workflow control-plane endpoint parity

- Active path now uses:
  - `GET /v3/projects/{project_id}/nodes/{node_id}/workflow-state`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/*`
  - `GET /v3/projects/{project_id}/events`
- Envelope handling remains unchanged (`ok/data` and typed error envelope path in client).

2. UX parity on `/chat-v2`

- Tab behavior and navigation remained stable in unit coverage.
- Audit shell behavior remained unchanged when review thread is unavailable.
- Action button gating and loading/mutation disable behavior remained intact.

3. Naming migration parity

- Canonical decision logic moved to `threadRole` for plan-ready gating.
- Temporary backward compatibility is preserved via fallback mapping from legacy `lane` when present.
- `lane_not_execution` suppression reason string kept for parity fixture compatibility while logic source moved to `threadRole`.

## Known Non-blocking Warnings

- React Router future-flag warnings in unit test output.
- Existing React `act(...)` warnings in some NodeDetailCard/TreeGraph tests.

These warnings predate Phase 5 scope and did not affect pass/fail criteria.

## Evidence Snapshot

- `npm run typecheck --prefix frontend` -> pass
- `npm run test:unit --prefix frontend` -> `38/38` files, `218/218` tests pass
- Guard search for active-path V2 workflow dependency -> no matches in active modules
