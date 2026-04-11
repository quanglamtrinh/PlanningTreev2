# Phase 7 Deprecation Notice - `/v2` Compatibility

Effective date: 2026-04-10

## Status

`/v3` is the canonical active conversation/workflow contract.

`/v2` routes are retained only for temporary compatibility and are now officially deprecated.

## Policy

- No new features will be added to `/v2`.
- No new client integrations should target `/v2`.
- `/v2` behavior is best-effort compatibility and may be removed in Phase 8 closeout.
- Canonical role naming for active clients is `threadRole`; `/v3` no longer emits `lane`.

## Client guidance

Use these `/v3` endpoints for active UI/runtime flows:

- `GET /v3/projects/{project_id}/nodes/{node_id}/workflow-state`
- `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/*`
- `GET /v3/projects/{project_id}/events`
- by-id conversation endpoints under `/v3/projects/{project_id}/threads/by-id/{thread_id}`

## Scope retained for compatibility

- `/v2` workflow routes remain mounted.
- `/v2` route wire shapes are retained as-is for backward compatibility during Phase 7.

## Planned removal window

- Phase 8 stabilization/closeout will decide and execute final `/v2` removal sequencing.
