# Phase 6: Execution and Audit Production Cutover

Status: not started.

## Goal

Cut execution and the full audit namespace to V2 in production without splitting the audit namespace across V1 and V2.

## In Scope

- production execution conversation path
- production audit namespace
- workflow bridge production enablement
- cutover monitoring and rollback plan

## Out of Scope

- ask-planning cutover
- hard cleanup of V1 files

## Preconditions

- Phase 5 complete
- no production audit writer remains on V1 helper paths
- V2 backend core and frontend path are validated in isolated rehearsal

## Checklist

- enable V2 routes and runtime for execution
- enable V2 routes and runtime for all audit producers
- confirm manual audit, rollup audit, frame/spec audit records, and auto-review persistence all land in V2
- enable workflow bridge production path
- confirm read-only rules still hold for execution and automated audit contexts
- monitor mismatch, reconnect, and error rates during rollout

## Verification

- targeted production-like integration pass
- smoke checks for execution feed, audit feed, workflow refresh, and audit system messages

## Exit Criteria

- execution uses V2 end to end
- audit namespace uses V2 end to end
- no audit producer writes V1 transcript state

## Artifacts To Produce

- `artifacts/phase-6/cutover-checklist.md`
- `artifacts/phase-6/smoke-results.md`
- `artifacts/phase-6/rollback-notes.md`
