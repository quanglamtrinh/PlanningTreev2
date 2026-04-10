# Phase 0 Decision Log

Date: 2026-04-10  
Status: locked

## Decision 1 - Phased naming transition to `thread_role`

Decision:

- Canonical V3 naming is `thread_role` with values `ask_planning | execution | audit`.
- Canonical JSON key in V3 payloads is `threadRole`.
- Sequencing lock to avoid foundation-vs-route conflict:
  - Phase 1: canonicalize domain/store naming to `threadRole`; normalize legacy `lane` on read.
  - Phase 3: `/v3` native route output is `threadRole`-primary; temporary `lane` dual-emit is allowed only as migration bridge.
  - Phase 5: frontend active path must stop reading `lane`.
  - Phase 7: remove `lane` emission and lane-based types/tests.

Implementation proposal:

1. Replace canonical backend domain/store naming with `threadRole` in Phase 1 without changing route behavior.
2. Keep read-compat for legacy payloads containing `lane` during migration.
3. Shift test gates by phase: route output gate in Phase 3, frontend lane-read removal in Phase 5, hard no-lane assertions in Phase 7.

## Decision 2 - Workflow control plane active path is V3-only

Decision:

- Primary frontend workflow control plane must call only:
  - `GET /v3/projects/{project_id}/nodes/{node_id}/workflow-state`
  - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/*`
  - `GET /v3/projects/{project_id}/events`
- `/v2` workflow APIs remain compatibility-only until cleanup.

Implementation proposal:

1. Add full V3 workflow control-plane endpoints in backend with locked envelope semantics.
2. Switch frontend workflow stores/event bridge to V3 endpoints by default.
3. Add grep/CI guard to block active-path references to `/v2/projects/.../workflow` and `/v2/projects/.../events`.

## Decision 3 - Compatibility bridge policy and rollout workflow

Decision:

- Bridge read policy is fixed: `read v3 first -> optional fallback read-through v2 -> persist v3`.
- New V3 path never writes back to V2.
- Bridge mode is explicit:
  - `enabled`: fallback allowed for all projects.
  - `allowlist`: fallback allowed only for listed projects.
  - `disabled`: no fallback; return `conversation_v3_missing` when V3 is absent.
- Disabled-mode error contract is fixed:
  - HTTP status: `409`
  - envelope: `{ "ok": false, "error": { "code": "conversation_v3_missing", "message": "...", "details": {} } }`
- Bridge mode configuration is env-only:
  - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE`
  - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST` (comma-separated project ids)

### Workflow example A - Legacy project with bridge enabled

1. Request hits a `/v3` thread query endpoint.
2. Service attempts to read `conversation_v3/{node_id}/{thread_role}.json`.
3. If absent, service reads legacy V2 snapshot source.
4. Service converts to canonical V3 payload (`threadRole`) and persists into `conversation_v3`.
5. Service returns V3 snapshot.
6. Subsequent requests serve from V3 directly.

### Workflow example B - Sunset state with bridge disabled

1. Request hits a `/v3` thread query endpoint.
2. Service attempts to read V3 snapshot.
3. If absent, service does not read V2.
4. Service returns typed `conversation_v3_missing`.
5. Operator runs migration and retries.

### Workflow example C - Controlled rollback with allowlist

1. Global bridge mode is `disabled`.
2. A temporary allowlist is enabled for selected project ids.
3. Only listed projects may fallback to V2 and then persist to V3.
4. Non-listed projects continue receiving `conversation_v3_missing`.
5. After validation, allowlist is removed and strict disabled mode resumes.

## Cross-track precedence note

- `docs/handoff/conversation-streaming-v2/progress.yaml` remains on an earlier migration track status.
- For native V3 end-to-end conversion, `docs/conversion/progress.yaml` is the authoritative tracker.

## Decision 4 - V3 workflow events endpoint ownership

Decision:

- Canonical backend ownership for `GET /v3/projects/{project_id}/events` is `backend/routes/workflow_v3.py`.
- During migration, `/v2` workflow events in `chat_v2.py` remain compatibility-only and must not remain on the primary active path after Phase 5.
