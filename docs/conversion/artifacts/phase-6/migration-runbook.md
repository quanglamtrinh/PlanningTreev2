# Phase 6 Migration Runbook

Date: 2026-04-10  
Owner: BE Conversion Track

## Objective

Migrate `conversation_v2` snapshots into canonical `conversation_v3` snapshots with idempotent reruns, per-target failure isolation, and bridge sunset readiness.

## Command

`python -m backend.tools.migrate_conversation_v2_to_v3`

Supported options:

- `--all-projects` or `--project-id <id>` (repeatable)
- `--node-id <id>` (repeatable)
- `--thread-role ask_planning|execution|audit` (repeatable)
- `--dry-run`
- `--report-json <path>`
- `--fail-fast-threshold <int>`
- `--data-root <path>`

## Report Contract

Every run emits a JSON report (stdout summary + optional `--report-json`) with frozen fields:

- `run_id`, `started_at`, `ended_at`
- `mode` (`dry-run` or `apply`)
- `bridge_mode` (env-derived at runtime)
- `totals`:
  - `scanned`
  - `migrated`
  - `skip_existing`
  - `skip_missing_v2`
  - `failed`
- `errors[]` (project/node/role scoped, typed with `error_type`)
- `checksum.targets_hash` (`sha256`), `checksum.target_count`

## Operational Workflow

1. Baseline safety check

- Confirm bridge config source is env-only:
  - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE`
  - `PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST`
- Keep mode at `enabled` during initial dry-run and first apply wave.

2. Dry-run

- `python -m backend.tools.migrate_conversation_v2_to_v3 --all-projects --dry-run --report-json docs/conversion/artifacts/phase-6/reports/dry-run.json`
- Review `totals`, `errors`, and `checksum`.

3. Apply migration

- `python -m backend.tools.migrate_conversation_v2_to_v3 --all-projects --report-json docs/conversion/artifacts/phase-6/reports/apply-run.json`
- Rerun apply command once more and verify idempotency (`migrated=0`, higher `skip_existing`).

4. Canary with `allowlist`

- Set `PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE=allowlist`.
- Set `PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST` to migrated projects only.
- Monitor stream/workflow errors and compare migration reports.

5. Sunset to `disabled`

- Set `PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE=disabled`.
- Validate missing V3 behavior returns typed `conversation_v3_missing` (HTTP 409), no V2 fallback.

## Rollback Policy

If disabled rollout exposes unexpected misses:

1. Immediate fallback: switch mode to `allowlist` or `enabled`.
2. Re-run migration for affected scope (`--project-id`, `--node-id`, `--thread-role`).
3. Re-attempt disabled mode after clean report and parity checks.

## Failure Handling

- Failures are isolated per `(project_id, node_id, thread_role)` target.
- Batch continues unless `failed > --fail-fast-threshold`.
- Typical outcomes:
  - `skip_existing`: V3 already present and readable.
  - `skip_missing_v2`: no V2 source for requested target.
  - `failed`: malformed/corrupt source JSON or unexpected read/write error.

## Verification Evidence (Implementation)

- `python -m pytest -q backend/tests/unit/test_conversation_v3_migration.py` -> `6 passed`
- `python -m pytest -q backend/tests/unit/test_conversation_v3_migration.py backend/tests/unit/test_thread_query_service_v3.py backend/tests/unit/test_conversation_v3_stores.py backend/tests/unit/test_conversation_v3_parity_fixtures.py` -> `18 passed`
- `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py backend/tests/integration/test_phase6_execution_audit_cutover.py backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_parity_fixtures.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py backend/tests/unit/test_ask_v3_rollout_phase6_7.py` -> `44 passed`
- Rehearsal run artifacts:
  - `docs/conversion/artifacts/phase-6/reports/rehearsal-dry-run.json`
  - `docs/conversion/artifacts/phase-6/reports/rehearsal-apply-wave1.json`
  - `docs/conversion/artifacts/phase-6/reports/rehearsal-apply-wave1-rerun.json`
  - `docs/conversion/artifacts/phase-6/reports/rehearsal-disabled-mode-check.json`
  - `docs/conversion/artifacts/phase-6/rehearsal-evidence.md`
