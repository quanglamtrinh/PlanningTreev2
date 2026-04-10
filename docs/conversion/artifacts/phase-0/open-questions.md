# Phase 0 Open Questions

Date: 2026-04-09  
Owner: PTM Core Team  
Status: resolved (none blocking for phase-0 close criteria)

| question | resolution | owner | resolved_on | blocking(Y/N) |
|---|---|---|---|---|
| What exact HTTP status and `error.details` shape should `conversation_v3_missing` use in disabled bridge mode? | Use `409` with typed code `conversation_v3_missing`; keep envelope shape with `error.details` as `{}` on active routes. | BE lead | 2026-04-09 | N |
| Where is bridge mode configured (`enabled|allowlist|disabled`) and where is allowlist stored/loaded? | Env-only control in Phase 2+: `PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE` and `PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST` (comma-separated project ids). | BE lead + Ops | 2026-04-09 | N |
| Which backend router owns canonical `/v3/projects/{project_id}/events` workflow events endpoint? | Canonical ownership is `backend/routes/workflow_v3.py`; no primary-path ownership in `chat_v2.py` after Phase 5 cutover. | BE lead | 2026-04-09 | N |

## Cross-track reconciliation note

- Legacy track file `docs/handoff/conversation-streaming-v2/progress.yaml` is still `phase_6_in_progress`.
- Conversion track source of truth is `docs/conversion/progress.yaml` and takes precedence for native V3 end-to-end scope.
- No immediate blocker from this mismatch for Phase 0; sequencing/naming reconciliation was recorded on 2026-04-10 in `docs/conversion/progress.yaml`.
