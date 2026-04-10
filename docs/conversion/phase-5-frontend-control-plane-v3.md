# Phase 5 - Frontend Control Plane V3

Status: pending  
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
- Remove unused/dead stores:
  - `threadStoreV2.ts`
  - `threadByIdStoreV2.ts` (after tests pass and imports are clean)

## 3. Out Of Scope

- Visual UX redesign
- Router rename (`chat-v2` -> another name) unless required later

## 4. Work Breakdown

- [ ] Build V3 workflow state store (zustand) and wire mutations.
- [ ] Build V3 workflow event bridge with reconnect handling.
- [ ] Update `BreadcrumbChatViewV2` to use new store/bridge.
- [ ] Remove primary-path calls to:
  - `buildWorkflowStatePathV2`
  - `buildWorkflowActionPathV2`
  - `buildProjectEventsUrlV2`
- [ ] Update telemetry hooks if needed.
- [ ] Remove unused imports/paths.
- [ ] Remove `lane`-based reads/types on primary transcript/workflow path (keep only temporary compat shim if strictly required during rollout).
- [ ] Update/add frontend unit tests for:
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

- [ ] `npm run typecheck --prefix frontend`
- [ ] `npm run test:unit --prefix frontend`
- [ ] Add grep-based guard tests to ensure no V2 workflow API references remain on active code paths.

## 8. Risks And Mitigations

- Risk: race conditions between stream updates and workflow refresh.
  - Mitigation: generation tokens and stale-response guards, consistent with thread store patterns.
- Risk: hidden V2 dependency in edge components.
  - Mitigation: enforce code-search gates before merge.
