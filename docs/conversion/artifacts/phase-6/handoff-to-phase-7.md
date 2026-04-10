# Phase 6 -> Phase 7 Handoff

Date: 2026-04-10  
From: Conversion Phase 6 (Batch Migration And Bridge Sunset)  
To: Conversion Phase 7 (Hard Cutover Cleanup)

## 1. Phase 6 Close Summary

Phase 6 is closed with migration tooling + operational rehearsal evidence complete.

- Migration CLI delivered:
  - `python -m backend.tools.migrate_conversation_v2_to_v3`
  - supports project/node/role filters, dry-run/apply, report JSON, fail-fast threshold
- Idempotency and failure-isolation validated by unit tests and rehearsal rerun
- Batch runbook + report template published
- Disabled bridge semantics validated at API-level:
  - HTTP `409`
  - `error.code = conversation_v3_missing`
  - `error.details = {}`

## 2. Phase 6 Evidence Artifacts

- `docs/conversion/artifacts/phase-6/migration-runbook.md`
- `docs/conversion/artifacts/phase-6/migration-report-template.json`
- `docs/conversion/artifacts/phase-6/rehearsal-evidence.md`
- `docs/conversion/artifacts/phase-6/reports/rehearsal-dry-run.json`
- `docs/conversion/artifacts/phase-6/reports/rehearsal-apply-wave1.json`
- `docs/conversion/artifacts/phase-6/reports/rehearsal-apply-wave1-rerun.json`
- `docs/conversion/artifacts/phase-6/reports/rehearsal-disabled-mode-check.json`

## 3. Locked Boundaries For Phase 7

1. Keep Phase-6 behavior contract intact while deleting legacy paths.
2. Do not regress `conversation_v3_missing` disabled-mode semantics.
3. Preserve canonical naming `threadRole` and complete lane cleanup only inside approved Phase-7 scope.
4. Remove V2 adapter dependencies from final `/v3` production path per locked decision `no_v2_adapter_in_v3_final`.

## 4. Phase 7 Initial Focus

- Remove dead/legacy adapter code after confirming migration safety.
- Finalize lane emission/type/test cleanup.
- Keep regression gates for by-id snapshot/events/turn/reset + workflow control-plane.

