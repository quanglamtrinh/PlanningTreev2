# Phase 5: Isolated Execution and Audit Rehearsal

Status: not started.

## Goal

Run the execution plus audit bundle end to end in an isolated environment before the first production cutover.

## In Scope

- isolated execution conversation path
- isolated audit persistence path
- workflow bridge behavior
- tool collapse and file-change final-list behavior
- user-input request and resolve behavior

## Out of Scope

- production traffic
- ask-planning cutover
- hard deletion of V1 code

## Checklist

- verify execution runtime begins and completes turns through `thread_runtime_service`
- verify audit namespace persistence uses only V2 abstractions
- verify `node_detail_service.py` frame and spec writes no longer use V1 immutable append helper
- verify `review_service.py` rollup package write no longer uses V1 immutable append helper
- verify raw tool call plus typed tool item never leaves duplicate tool items
- verify file-change previews are overwritten by `outputFilesReplace`
- verify user-input requested and resolved flows survive reload and reconnect
- verify workflow bridge refreshes detail state without conversation reducer hacks
- run only on fixture replay or isolated sandbox workspace

## Verification

- end-to-end rehearsal evidence
- targeted integration tests
- explicit code-search or runtime assertions for no V1 audit writers

## Exit Criteria

- no production-path audit writer remains on V1 helper paths
- no rehearsal path touches the production workspace
- execution and audit bundle behaves correctly on canonical V2 contracts

## Artifacts To Produce

- `artifacts/phase-5/rehearsal-runbook.md`
- `artifacts/phase-5/rehearsal-results.md`
- `artifacts/phase-5/no-v1-audit-writers-check.md`
