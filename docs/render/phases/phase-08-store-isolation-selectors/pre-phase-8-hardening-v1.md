# Pre-Phase-8 Hardening v1

Status: Completed.

Date: 2026-04-13.

Scope: H1 evidence integrity, H2 reload contract hardening, H3 pre-split selector guardrails.

## 1. Hardening Checklist

- [x] Phase 07 source evidence scripts require candidate input by default.
- [x] `--allow-synthetic` mode is explicitly marked `gate_eligible=false`.
- [x] Source evidence includes:
  - `evidence_mode`
  - `gate_eligible`
  - `context.candidate_path` (required for candidate mode)
  - `context.candidate_commit_sha` (required for candidate mode)
- [x] Phase 07 gate report enforces candidate-backed eligibility.
- [x] Frontend forced reload paths use typed `ReloadReasonCode`.
- [x] No forced reload path allows null reason.
- [x] Guardrail selector entrypoints exist (`selectCore`, `selectTransport`, `selectUiControl`).

## 2. Evidence Runbook

Set candidate SHA:

`$env:PTM_CANDIDATE_COMMIT_SHA = "<candidate_sha>"`

Candidate evidence (gate-eligible):

1. `python scripts/phase07_state_hot_path_benchmark.py --candidate <candidate_metrics.json> --self-test --output docs/render/phases/phase-07-state-shape-hot-path/evidence/state_hot_path_benchmark.json`
2. `python scripts/phase07_state_hot_path_trace.py --candidate <candidate_trace.json> --self-test --output docs/render/phases/phase-07-state-shape-hot-path/evidence/state_hot_path_trace.json`
3. `python scripts/phase07_reducer_identity_tests.py --candidate <candidate_identity.json> --self-test --output docs/render/phases/phase-07-state-shape-hot-path/evidence/reducer_identity_tests.json`
4. `python scripts/phase07_gate_report.py --self-test --output docs/render/phases/phase-07-state-shape-hot-path/evidence/phase07-gate-report.json`

Synthetic dry-run only (not gate-eligible):

1. `python scripts/phase07_state_hot_path_benchmark.py --allow-synthetic --self-test --output <tmp_benchmark.json>`
2. `python scripts/phase07_state_hot_path_trace.py --allow-synthetic --self-test --output <tmp_trace.json>`
3. `python scripts/phase07_reducer_identity_tests.py --allow-synthetic --self-test --output <tmp_identity.json>`
4. `python scripts/phase07_gate_report.py --self-test --output <tmp_gate_report.json>` (expected fail because sources are synthetic)

## 3. Frontend Validation Runbook

1. `npm run typecheck --prefix frontend`
2. `npm run test:unit --prefix frontend -- applyThreadEventV3.test.ts threadByIdStoreV3.test.ts`

## 4. Phase-8 Entry Preconditions

1. Candidate-backed Phase 07 evidence regenerated and gate report passes.
2. Reload reason taxonomy remains unchanged unless contract update is approved.
3. New selector work in Phase 08 must build on guardrail selectors, not bypass them.
