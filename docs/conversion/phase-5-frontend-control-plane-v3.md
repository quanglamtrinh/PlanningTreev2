# Phase 5 - Frontend Control Plane V3

Status: completed  
Estimate: 6-8 person-days (14%)

## 1. Objective

Migrate the primary frontend surface (`/chat-v2`) to full V3 for transcript and workflow control plane:

- workflow state
- workflow actions
- workflow event bridge
- remove active-path reads of legacy `lane` in favor of canonical `threadRole`

No `/v2/projects/...` dependency should remain on the primary active path.

## 2. In Scope

- API client:
  - add/replace workflow APIs under the `/v3` namespace according to the locked contract
  - allowed endpoints:
    - `GET /v3/projects/{project_id}/nodes/{node_id}/workflow-state`
    - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/finish-task`
    - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-execution`
    - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/review-in-audit`
    - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-audit`
    - `POST /v3/projects/{project_id}/nodes/{node_id}/workflow/improve-in-execution`
    - `GET /v3/projects/{project_id}/events`
- Store migration:
  - `workflowStateStoreV2` -> V3 workflow store
  - event bridge `/v2/projects/{id}/events` -> `GET /v3/projects/{project_id}/events`
- `BreadcrumbChatViewV2` wiring updates
- Keep V2 compatibility modules/builders available, but remove active-path imports/usages from primary `chat-v2` wiring.

## 3. Out Of Scope

- Visual UX redesign
- Router rename (`chat-v2` -> another name) unless required later

## 4. Work Breakdown

- [x] Build V3 workflow state store (zustand) and wire mutations.
- [x] Build V3 workflow event bridge with reconnect handling.
- [x] Update `BreadcrumbChatViewV2` to use new store/bridge.
- [x] Remove primary-path calls to:
  - `buildWorkflowStatePathV2`
  - `buildWorkflowActionPathV2`
  - `buildProjectEventsUrlV2`
- [x] Update telemetry hooks if needed.
- [x] Remove unused imports/paths.
- [x] Remove `lane`-based reads/types on primary transcript/workflow path (keep only temporary compat shim if strictly required during rollout).
- [x] Update/add frontend unit tests for:
  - tab resolution
  - action button gating
  - reconnect and reload behavior

## 5. Deliverables

- Frontend control-plane V3 path is on by default.
- Artifacts:
  - `docs/conversion/artifacts/phase-5/frontend-migration-checklist.md`
  - `docs/conversion/artifacts/phase-5/frontend-regression-notes.md`

## 6. Exit Criteria

- Frontend no longer calls:
  - `/v2/projects/{projectId}/nodes/{nodeId}/workflow-state`
  - `/v2/projects/{projectId}/nodes/{nodeId}/workflow/*`
  - `/v2/projects/{projectId}/events`
  on the primary surface.
- Frontend uses only the workflow endpoints defined in `docs/conversion/workflow-v3-control-plane-contract.md`.
- Primary active route no longer depends on `workflowStateStoreV2` or V2 project events bridge.
- Frontend unit tests related to `chat-v2`/workflow pass.

## 7. Verification

- [x] `npm run typecheck --prefix frontend`
- [x] `npm run test:unit --prefix frontend`
- [x] Add grep-based guard tests to ensure no V2 workflow API references remain on active code paths.

## 8. Risks And Mitigations

- Risk: race conditions between stream updates and workflow refresh.
  - Mitigation: generation tokens and stale-response guards, consistent with thread store patterns.
- Risk: hidden V2 dependency in edge components.
  - Mitigation: enforce code-search gates before merge.

## 9. Implementation Snapshot (2026-04-10)

- Active `chat-v2` workflow control-plane now uses:
  - `useWorkflowStateStoreV3`
  - `useWorkflowEventBridgeV3`
  - V3 workflow endpoints in API client
- `ThreadSnapshotV3` now uses canonical `threadRole` on FE type contract.
- `lane` remains optional compatibility field only (deprecated) and no longer drives active plan-ready decisions.
- Phase 5 artifacts published:
  - `docs/conversion/artifacts/phase-5/frontend-migration-checklist.md`
  - `docs/conversion/artifacts/phase-5/frontend-regression-notes.md`
