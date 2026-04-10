# Phase 0 Open Questions

Date: 2026-04-09  
Owner: PTM Core Team  
Status: tracked (none blocking for phase-0 close criteria)

| question | impact | owner | deadline | blocking(Y/N) |
|---|---|---|---|---|
| What exact HTTP status and `error.details` shape should `conversation_v3_missing` use in disabled bridge mode? | Needed for deterministic API tests and FE error handling in Phase 2/3. | BE lead | Before Phase 2 implementation merge | N |
| Where is bridge mode configured (`enabled|allowlist|disabled`) and where is allowlist stored/loaded? | Needed for operational runbook and rollback toggles in Phase 2/6. | BE lead + Ops | Before Phase 2 implementation merge | N |
| Which backend router owns canonical `/v3/projects/{project_id}/events` workflow events endpoint? | Needed to avoid duplicate ownership and contract drift in Phase 3/5. | BE lead | Before Phase 3 route cutover merge | N |

## Cross-track reconciliation note

- Legacy track file `docs/handoff/conversation-streaming-v2/progress.yaml` is still `phase_6_in_progress`.
- Conversion track source of truth is `docs/conversion/progress.yaml` and takes precedence for native V3 end-to-end scope.
- No immediate blocker from this mismatch for Phase 0; reconcile status references before Phase 1 implementation kickoff.
