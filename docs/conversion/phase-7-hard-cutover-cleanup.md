# Phase 7 - Hard Cutover Cleanup

Status: pending  
Estimate: 4-5 person-days (8%)

## 1. Objective

Remove V2 adapter paths from production code after the system is stable.

## 2. In Scope

- Remove or hard-deprecate:
  - `thread_query_service_v2` production wiring
  - `thread_runtime_service_v2` production wiring
  - `project_v2_snapshot_to_v3` and `project_v2_envelope_to_v3` on production route paths
  - legacy `lane` compatibility branches in V3 snapshot/event serializers
  - frontend dead stores that are V2-only
- Rename services/state to clearly indicate "V3 canonical."
- Update primary architecture documentation.

## 3. Out Of Scope

- New features
- New rollout experiments

## 4. Work Breakdown

- [ ] Clean DI in `backend/main.py` so canonical paths no longer use `_v2` naming.
- [ ] Remove unused compatibility code branches.
- [ ] Add code-search gates:
  - no V2 core calls from `/v3` paths
  - no active frontend workflow calls to `/v2`
- [ ] Update tests to match new canonical naming.
- [ ] Define deprecation strategy for V2 APIs if route compatibility is still retained.

## 5. Deliverables

- Large cleanup pull request (with checklists)
- Artifacts:
  - `docs/conversion/artifacts/phase-7/deletion-log.md`
  - `docs/conversion/artifacts/phase-7/deprecation-notice.md`

## 6. Exit Criteria

- Code search confirms no V2 adapter dependencies on production paths.
- Test gates pass after cleanup.
- Architecture docs reflect native V3 end-to-end reality.

## 7. Verification

- [ ] Full targeted backend suite for conversation/workflow
- [ ] Frontend typecheck and unit tests
- [ ] Search-gate scripts (rg-based) pass

## 8. Risks And Mitigations

- Risk: deleting code too early causes hidden edge-case regressions.
  - Mitigation: run cleanup only after Phase 6 stabilization proof.
- Risk: hidden transitive V2 imports.
  - Mitigation: enforce forbidden-import checks in CI.
