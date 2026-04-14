# Phase 10 Preflight v1

Status: Frozen implementation preflight.

Date: 2026-04-13.

Phase: `phase-10-progressive-virtualized-rendering` (D03, D04, D09).

## 1. Entry Criteria Lock

`phase_09_passed` evidence:

- `docs/render/phases/phase-09-row-isolation-cache/evidence/phase09-gate-report.json`

`list_anchor_invariants_frozen` artifact:

- `docs/render/phases/phase-10-progressive-virtualized-rendering/list-anchor-invariants-v1.md`

## 2. Frozen Decisions for Implementation

1. Virtualization unit:
   - v1 virtualizes `groupedEntries` directly (no flatten migration in initial pass).
2. Anchor policy:
   - prepend/load-more must preserve viewport anchor and visible reading position.
   - auto-pin to bottom is allowed only when viewport is already near bottom before update.
3. Correctness fallback:
   - on invariant break, degrade to safe non-virtualized rendering mode.
   - correctness is prioritized over render throughput.
4. Render budget guard:
   - budget adaptation may reduce per-frame batch/decorations only.
   - budget adaptation must not change ordering/key determinism.

## 3. Rollout Mode Contract

Feature flag: `ptm_phase10_progressive_virtualization_mode`

- `off`: existing full render behavior.
- `shadow`: collect metrics and validate anchor logic without virtualization-authoritative behavior.
- `on`: progressive + virtualization + budget guard active.

Default for implementation start: `off`.

## 4. Compatibility and Non-Goals

Compatibility lock:

- no C1 event envelope changes.
- no C2 replay/cursor semantics changes.
- no C3 lifecycle state machine changes.
- no C4 durability boundary changes.
- no C6 queue flow changes.

Non-goals:

- no Layer F observability expansion.
- no Layer G rollout/safety expansion beyond explicit mode contract above.

## 5. Gate and Evidence Lock

Phase 10 source harness:

1. `scripts/phase10_long_thread_open_scenario.py`
2. `scripts/phase10_scroll_smoothness_profile.py`
3. `scripts/phase10_virtualization_anchor_tests.py`

Phase 10 gate aggregation:

1. `scripts/phase10_gate_report.py`

Canonical outputs:

1. `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/long_thread_open_scenario.json`
2. `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/scroll_smoothness_profile.json`
3. `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/virtualization_anchor_tests.json`
4. `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/phase10-gate-report.json`

Evidence eligibility lock:

1. `candidate` evidence with `gate_eligible=true` is required for closure.
2. `synthetic` evidence with `gate_eligible=false` is allowed for local dry-run only.

Reference commands:

1. synthetic dry-run source generation:
   - `python scripts/phase10_long_thread_open_scenario.py --allow-synthetic --self-test`
   - `python scripts/phase10_scroll_smoothness_profile.py --allow-synthetic --self-test`
   - `python scripts/phase10_virtualization_anchor_tests.py --allow-synthetic --self-test`
2. candidate-backed source generation:
   - `python scripts/phase10_long_thread_open_scenario.py --self-test --candidate docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/candidates/long-thread-open-scenario-candidate.json --candidate-commit-sha <sha>`
   - `python scripts/phase10_scroll_smoothness_profile.py --self-test --candidate docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/candidates/scroll-smoothness-profile-candidate.json --candidate-commit-sha <sha>`
   - `python scripts/phase10_virtualization_anchor_tests.py --self-test --candidate docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/candidates/virtualization-anchor-tests-candidate.json --candidate-commit-sha <sha>`
3. gate evaluation:
   - `python scripts/phase10_gate_report.py --self-test --candidate docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/candidates/long-thread-open-scenario-candidate.json`

## 6. Preflight Exit

No open preflight blocker remains for Phase 10 implementation kickoff under frozen contracts and defaults in this document.
