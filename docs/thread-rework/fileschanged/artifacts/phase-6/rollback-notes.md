# Phase 6 Rollback Notes (Release-level)

Date: 2026-04-04

## Rollback model

Observe-only rollout uses release rollback, not runtime feature toggles.

## Trigger conditions

- persistent file-change render failures in execution threads on new turns
- repeated empty file-change cards for turns that carry canonical `changes[]` with diff
- critical regression in patch/apply workflow related to file-change projection

## Rollback procedure

1. Identify offending release SHA and affected environment ring.
2. Revert release commit set (or redeploy last known good release artifact).
3. Deploy rollback artifact through normal release pipeline.
4. Validate rollback with minimum smoke:
   - commandExecution still renders command card
   - fileChange card expands correctly on known-good scenario
   - no critical render/apply error spike
5. Record rollback note in release changelog and issue tracker.

## Post-rollback follow-up

- isolate regression with targeted unit/integration test reproduction
- patch forward with explicit test guard
- re-run internal -> canary -> broad observe-only sequence
