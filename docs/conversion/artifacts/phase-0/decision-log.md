# Phase 0 Decision Log

Date: 2026-04-10  
Status: locked

## Decision 1 - Immediate naming cutover to `thread_role`

Decision:

- Canonical V3 naming is `thread_role` with values `ask_planning | execution | audit`.
- Canonical JSON key in V3 payloads is `threadRole`.
- Active V3 APIs must not emit legacy `lane`.

Implementation proposal:

1. Replace `ThreadSnapshotV3.lane` with `ThreadSnapshotV3.threadRole` in backend and frontend V3 types.
2. Keep read-compat for legacy payloads containing `lane` during migration only.
3. Add tests that fail if active V3 payloads still include `lane`.

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
