# Phase 11 - Heavy Compute Off Main Thread

Status: Completed (all P11 gates passed with candidate-backed evidence).

Date: 2026-04-14.

Scope IDs: D05, D06, D07.

Subphase workspace: ./subphases/.

Frozen preflight artifacts:

1. `preflight-v1.md`
2. `worker-result-versioning-policy-v1.md` (`worker_result_versioning_policy_frozen`)

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Offloads expensive UI compute while keeping deterministic rendering semantics.

Contract focus:

- Primary: `C5` Frontend State Contract v1

Must-hold decisions:

- Worker paths must use version tokens and discard stale async results.
- Fallback sync path must remain behaviorally equivalent.
- Off-main-thread optimization cannot alter message semantics.

## Objective

Prevent main-thread stalls from markdown/diff/command-output heavy rows.

## In Scope

1. D05: Lazy markdown rendering.
2. D06: Workerized diff parse/highlight.
3. D07: Incremental command output tail updates.

## Implemented Scope

### 1. Lazy markdown scheduling (D05)

Implemented visibility-driven markdown scheduling with deferred fallback:

- visible rows render markdown eagerly
- offscreen rows defer parse until intersection hit or deferred timeout
- semantic content is preserved; only scheduling changed

### 2. Workerized diff artifacts (D06)

Implemented worker protocol/runtime and guarded apply flow:

- worker protocol v1 with `schemaVersion`, `jobId`, `requestSeq`, and artifact envelope
- stale-drop enforcement via version token and per-token latest `requestSeq`
- sync fallback on worker timeout/error/postMessage failure
- rollout modes enforced (`off`, `shadow`, `on`)

### 3. Incremental command output tail (D07)

Implemented append-aware incremental tail cache:

- append-only updates process delta instead of full split per patch
- non-append mutation/freshness boundary triggers deterministic rebuild
- display semantics and trailing line cap remain unchanged

## Runtime Controls

Environment flags:

1. `VITE_PTM_PHASE11_HEAVY_COMPUTE_MODE` (`off` | `shadow` | `on`)
2. `VITE_PTM_PHASE11_WORKER_DIFF_THRESHOLD_CHARS`
3. `VITE_PTM_PHASE11_WORKER_TIMEOUT_MS`

Default worker offload thresholds:

1. payload size `>= 8 KB`, or
2. payload line count `>= 400`.

Mode semantics:

1. `off`: sync path only.
2. `shadow`: worker executes but UI applies sync artifacts only.
3. `on`: worker apply is allowed only when version-token freshness check passes.

## Quality Gates

1. Main-thread health:
   - reduced long tasks during heavy diff/markdown streams.
2. Render correctness:
   - parsed output remains equivalent to baseline.
3. Fallback reliability:
   - worker failure path remains functional.

## Test Plan

1. Unit tests:
   - incremental tail update correctness.
   - worker message protocol and error fallback.
2. Integration tests:
   - large diff and large markdown scenarios.
3. Manual checks:
   - UI remains interactive while heavy content arrives.

Gate harness scripts:

1. `scripts/phase11_heavy_payload_profile.py`
2. `scripts/phase11_worker_versioning_tests.py`
3. `scripts/phase11_heavy_content_interaction_smoke.py`
4. `scripts/phase11_gate_report.py`

## Validation Snapshot

Executed checks:

1. `npm run typecheck --prefix frontend` -> `PASS`.
2. `npx vitest run tests/unit/parseArtifactCache.test.ts tests/unit/commandOutputTail.test.ts tests/unit/ConversationMarkdown.lazy.test.tsx tests/unit/MessagesV3.test.tsx tests/unit/messagesV3.phase10.test.tsx tests/unit/ConversationMarkdown.desktop-hooks.test.tsx tests/unit/MessagesV3ErrorBoundary.test.tsx` -> `PASS`.
3. `npm run check:render_freeze` -> `PASS`.
4. candidate-backed evidence source scripts:
   - `python scripts/phase11_heavy_payload_profile.py --self-test --candidate docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/candidates/heavy-payload-profile-candidate.json --candidate-commit-sha 5a8d45a792dc` -> `PASS`.
   - `python scripts/phase11_worker_versioning_tests.py --self-test --candidate docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/candidates/worker-versioning-tests-candidate.json --candidate-commit-sha 5a8d45a792dc` -> `PASS`.
   - `python scripts/phase11_heavy_content_interaction_smoke.py --self-test --candidate docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/candidates/heavy-content-interaction-smoke-candidate.json --candidate-commit-sha 5a8d45a792dc` -> `PASS`.
5. candidate-backed gate aggregation:
   - `python scripts/phase11_gate_report.py --self-test --candidate docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/candidates` -> `PASS`.

## Exit Gates (P11) Status

Gate targets come from `docs/render/system-freeze/phase-gates-v1.json`.

| Gate | Metric | Target | Current value | Status |
|---|---|---|---|---|
| P11-G1 | main_thread_long_task_reduction_pct | `>= 50` | `56.4` | pass |
| P11-G2 | stale_worker_result_applies | `<= 0` | `0.0` | pass |
| P11-G3 | interaction_freeze_events_over_50ms | `<= 0` | `0.0` | pass |

Required evidence files for closure:

- `docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/heavy_payload_profile.json`
- `docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/worker_versioning_tests.json`
- `docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/heavy_content_interaction_smoke.json`
- `docs/render/phases/phase-11-heavy-compute-off-main-thread/evidence/phase11-gate-report.json`

## Risks and Mitigations

1. Risk: worker serialization overhead offsets gains for small payloads.
   - Mitigation: threshold-based worker offload.
2. Risk: ordering mismatch between async worker results and live stream.
   - Mitigation: version token per item update and stale result discard.

## Handoff to Phase 12

After compute offload, data volume governance can further reduce rendering pressure at source.

Handoff and closeout artifacts:

- `close-phase-v1.md`
- `handoff-to-phase-12.md`

## Effort Estimate

- Size: Large
- Estimated duration: 6-8 engineering days
- Suggested staffing: 1 frontend primary + 1 backend/desktop support
- Confidence level: Medium (depends on current code-path complexity and test debt)
