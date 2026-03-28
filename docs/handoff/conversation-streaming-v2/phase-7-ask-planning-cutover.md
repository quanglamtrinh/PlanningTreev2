# Phase 7: Ask-Planning Cutover

Status: not started.

## Goal

Move ask-planning onto the same V2 runtime, snapshot contract, and frontend rendering path used by execution and audit.

## In Scope

- ask-planning runtime entry path
- ask-planning V2 store and routes
- retirement of dual-read transcript handling

## Out of Scope

- hard deletion of V1 code
- post-cutover cleanup unrelated to ask-planning

## Checklist

- route ask-planning through the shared V2 runtime and query services
- ensure `POST /turns` creates the local user item and then enters shared turn lifecycle
- remove ask-planning dependency on V1 transcript state
- confirm user-input resolution works in the interactive ask flow
- confirm reload and reconnect behavior matches audit and execution

## Verification

- targeted backend integration tests for ask-planning
- frontend UI tests for interactive sending, waiting-user-input, and error paths

## Exit Criteria

- ask-planning uses the same canonical item model as audit and execution
- no dual-read transcript path remains for ask-planning
- main frontend ask view can run entirely on V2

## Artifacts To Produce

- `artifacts/phase-7/ask-cutover-checklist.md`
- `artifacts/phase-7/interactive-smoke-results.md`
