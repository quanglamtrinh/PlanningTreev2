# Phase 6 - Data Migration And Compatibility Bridge

Status: pending  
Estimate: 4-6 person-days (10%)

## 1. Muc tieu

Chuyen du lieu transcript tu `conversation_v2` sang `conversation_v3` an toan, co rollback, co idempotency.

## 2. In-scope

- Migration script/service:
  - scan project nodes + roles
  - convert snapshot V2 -> snapshot V3
  - write `conversation_v3`
  - marker migration version
- Dry-run mode + report mode.
- Compatibility bridge co thoi han:
  - neu chua migrated thi co the bootstrap tu V2 (chi doc)
- Runbook rollout theo batch.

## 3. Out-of-scope

- Hard delete V2 store file.
- Remove toan bo V2 code.

## 4. Work breakdown

- [ ] Tao migration command:
  - de nghi: `python -m backend.tools.migrate_conversation_v2_to_v3`
- [ ] Ho tro mode:
  - `--project-id`
  - `--all-projects`
  - `--dry-run`
  - `--report-json`
- [ ] Bao toan behavior:
  - lane mapping ask_planning -> ask
  - hidden audit seed item policy
  - planReady/userInput signals
- [ ] Log migration stats:
  - total snapshots scanned
  - converted
  - skipped
  - failed
- [ ] Tao rollback note:
  - cach disable V3 read path
  - cach fallback to V2 snapshot path tam thoi

## 5. Deliverables

- Migration tool + tests.
- Artifact:
  - `docs/conversion/artifacts/phase-6/migration-runbook.md`
  - `docs/conversion/artifacts/phase-6/migration-report-template.json`

## 6. Exit criteria

- Tool migration idempotent (chay lai khong doi data da migrated).
- Dry-run va real-run tren sample project pass.
- Co bao cao migration truoc rollout production.

## 7. Verification

- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_migration.py` (new)
- [ ] `python -m pytest -q backend/tests/unit/test_conversation_v3_parity_fixtures.py`
- [ ] Rehearsal run voi project mau + compare checksum report.

## 8. Risks va giam thieu

- Risk: snapshot V2 malformed trong workspace cu.
  - Mitigation: tolerant parser + per-node failure isolation + report.
- Risk: partial migration dang do.
  - Mitigation: write temp file + atomic rename + migration marker transaction.

