# Phase 7 Deprecation Notice - `/v2` Compatibility (Superseded in Phase 8)

Effective date: 2026-04-10

## Status

`/v3` is the canonical active conversation/workflow contract.

As of Phase 8 closeout, `/v2` routes are hard removed from backend API mounts.

## Policy

- No new features will be added to `/v2`.
- No new client integrations should target `/v2`.
- `/v2` behavior is no longer available on backend API routes after Phase 8 (`404` for `/v2/**`).
- Canonical role naming for active clients is `threadRole`; `/v3` no longer emits `lane`.

## Client guidance

Use these `/v3` endpoints for active UI/runtime flows:

- `GET /v3/projects/{project_id}/nodes/{node_id}/workflow-state`
- `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/*`
- `GET /v3/projects/{project_id}/events`
- by-id conversation endpoints under `/v3/projects/{project_id}/threads/by-id/{thread_id}`

## Final Removal Outcome

- `/v2` workflow and conversation route mounts were removed in Phase 8.
- Any remaining `/v2` references in historical docs are archival context only.
