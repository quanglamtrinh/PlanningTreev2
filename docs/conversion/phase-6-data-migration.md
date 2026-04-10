# Phase 6 - Batch Migration And Bridge Sunset

Status: in_progress  
Estimate: 4-6 person-days (10%)

## 1. Objective

Complete batch transcript migration from `conversation_v2` to `conversation_v3`, then safely sunset the compatibility bridge.

## 2. In Scope

- Migration script/service:
  - scan project nodes and roles
  - convert V2 snapshots -> V3 snapshots
  - write `conversation_v3`
  - write migration-version marker
- Dry-run mode and report mode
- Compatibility bridge sunset plan:
  - define exact bridge-disable conditions
  - define rollback policy if temporary bridge re-enable is needed
  - enforce bridge modes `enabled -> allowlist -> disabled`
  - enforce typed error `conversation_v3_missing` when disabled and V3 snapshot is absent
- Batch rollout runbook

## 3. Out Of Scope

- Hard deletion of V2 store files
- Full removal of all V2 code

## 4. Work Breakdown

- [ ] Create migration command:
  - proposed: `python -m backend.tools.migrate_conversation_v2_to_v3`
- [ ] Support modes:
  - `--project-id`
  - `--all-projects`
  - `--dry-run`
  - `--report-json`
- [ ] Preserve behavior:
  - consistent `thread_role` naming (`ask_planning | execution | audit`)
  - hidden audit seed-item policy
  - `planReady` and `userInput` signals
- [ ] Log migration stats:
  - total snapshots scanned
  - converted
  - skipped
  - failed
- [ ] Write rollback notes:
  - how to enable/disable the compatibility bridge
  - how to scope temporary fallback with allowlist mode
  - how to roll back if a batch migration fails

## 5. Deliverables

- Migration tool and tests
- Artifacts:
  - `docs/conversion/artifacts/phase-6/migration-runbook.md`
  - `docs/conversion/artifacts/phase-6/migration-report-template.json`

## 6. Exit Criteria

- Migration tool is idempotent (re-running does not modify already migrated data).
- Dry-run and real-run pass on sample projects.
- Migration report exists before production rollout.
- Bridge-sunset criteria are explicit and validated through sample rollout dry-runs.
- Disabled-mode behavior (`conversation_v3_missing` with no V2 fallback) is validated in rehearsal.

## 7. Verification

- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_migration.py` (new)
- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_parity_fixtures.py`
- [ ] Rehearsal run on sample projects with checksum comparison report.

## 8. Risks And Mitigations

- Risk: malformed V2 snapshots in old workspaces.
  - Mitigation: tolerant parser, per-node failure isolation, and reporting.
- Risk: interrupted partial migration.
  - Mitigation: write temp files, then atomic rename, plus migration-marker transaction.
- Risk: bridge disabled too early and rare fallback cases break.
  - Mitigation: sunset by canary waves and monitor stream/workflow error rates.
