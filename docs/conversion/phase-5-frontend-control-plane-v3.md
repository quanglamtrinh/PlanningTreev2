# Phase 5 - Frontend Control Plane V3

Status: pending  
Estimate: 6-8 person-days (14%)

## 1. Muc tieu

Frontend surface chinh (`/chat-v2`) dung full V3 cho transcript + workflow control plane:

- workflow state
- workflow actions
- workflow event bridge

Khong con dependency `/v2/projects/...` tren duong chay chinh.

## 2. In-scope

- API client:
  - add/replace workflow APIs sang `/v3` namespace (neu backend expose)
- Store migration:
  - `workflowStateStoreV2` -> workflow store V3
  - event bridge `/v2/projects/{id}/events` -> V3 equivalent
- `BreadcrumbChatViewV2` wiring update.
- Remove dead stores khong con su dung:
  - `threadStoreV2.ts`
  - `threadByIdStoreV2.ts` (sau khi test va imports clean)

## 3. Out-of-scope

- Redesign visual UX.
- Router rename (`chat-v2` -> khac) neu chua can thiet.

## 4. Work breakdown

- [ ] Tao workflow state store V3 (zustand) va wiring mutation.
- [ ] Tao workflow event bridge V3 + reconnect handling.
- [ ] Cap nhat `BreadcrumbChatViewV2` su dung store/bridge moi.
- [ ] Cap nhat telemetry hooks neu can.
- [ ] Remove import/path thua.
- [ ] Cap nhat/bo sung unit tests FE cho:
  - tab resolution
  - action button gating
  - reconnect + reload behavior

## 5. Deliverables

- FE control-plane V3 path chay on by default.
- Artifacts:
  - `docs/conversion/artifacts/phase-5/frontend-migration-checklist.md`
  - `docs/conversion/artifacts/phase-5/frontend-regression-notes.md`

## 6. Exit criteria

- Frontend khong con call:
  - `/v2/projects/{projectId}/nodes/{nodeId}/workflow-state`
  - `/v2/projects/{projectId}/nodes/{nodeId}/workflow/*`
  - `/v2/projects/{projectId}/events`
  tren surface chinh.
- Unit tests FE lien quan chat-v2/workflow pass.

## 7. Verification

- [ ] `npm run typecheck --prefix frontend`
- [ ] `npm run test:unit --prefix frontend`
- [ ] Them test grep guard khong con references V2 workflow API trong code path active.

## 8. Risks va giam thieu

- Risk: race condition stream/workflow refresh.
  - Mitigation: generation tokens + stale response guard nhu thread store.
- Risk: hidden dependency V2 trong edge component.
  - Mitigation: code search gate truoc merge.

