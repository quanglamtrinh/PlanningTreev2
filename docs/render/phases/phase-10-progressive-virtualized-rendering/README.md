# Phase 10 - Progressive and Virtualized Rendering

Status: Completed (all P10 gates passed with candidate-backed evidence).

Date: 2026-04-14.

Scope IDs: D03, D04, D09.

Subphase workspace: ./subphases/.

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- Improves large-thread UX after state-level correctness and isolation are in place.

Contract focus:

- Primary: `C5` Frontend State Contract v1

Must-hold decisions:

- Virtualization must preserve anchor/load-more invariants.
- Progressive rendering must not break deterministic ordering.
- Budget degradation logic must preserve correctness before aesthetics.

## Objective

Keep long-thread interaction smooth by limiting mount pressure and controlling frame-time budget.

Frozen preflight artifacts:

1. `preflight-v1.md`
2. `list-anchor-invariants-v1.md` (`list_anchor_invariants_frozen`)

## In Scope

1. D03: Progressive rendering for long history.
2. D04: Virtualization for very long feeds.
3. D09: Render budget guard.

## Implemented Scope

### 1. Progressive row mount (D03)

Implemented in `MessagesV3` with frozen defaults:

- threshold: `groupedEntries.length >= 250`
- initial chunk: `120` groups
- per-frame batch: `40` groups with adaptive degrade limits
- rollout mode support: `off -> shadow -> on`
- deterministic order and row identity preserved

### 2. Viewport virtualization (D04)

Implemented with `@tanstack/react-virtual`:

- virtualization unit v1: `groupedEntries` (no flatten)
- activation threshold: `groupedEntries.length >= 300` when mode=`on`
- stable keys: `item.id` and `toolGroup.id`
- dynamic measurement via `measureElement`
- correctness fallback latch to safe non-virtualized path on anchor invariant break

### 3. Render budget guard (D09)

Implemented adaptive guard with correctness-first policy:

- level 1 on sustained slow frames: reduce batch + overscan
- level 2 on sustained severe slow frames: stronger batch/overscan reduction + defer non-critical decorations
- recovery path on stable frame window
- no change to content semantics or ordering

Gate harness:

1. `scripts/phase10_long_thread_open_scenario.py`
2. `scripts/phase10_scroll_smoothness_profile.py`
3. `scripts/phase10_virtualization_anchor_tests.py`
4. `scripts/phase10_gate_report.py`

Evidence contract:

- `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/README.md`

## Implemented Code Areas

Frontend render path:

- `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
- `frontend/src/features/conversation/components/v3/MessagesV3.module.css`
- `frontend/src/features/conversation/components/v3/messagesV3ProfilingHooks.ts`
- `frontend/src/vite-env.d.ts`
- `frontend/package.json`

Tests:

- `frontend/tests/unit/messagesV3.phase10.test.tsx`
- `frontend/tests/unit/MessagesV3.test.tsx`
- `frontend/tests/unit/messagesV3.profiling-hooks.test.tsx`
- `frontend/tests/unit/messagesV3.utils.test.ts`

## Validation Snapshot

Executed checks:

1. `npm run typecheck --prefix frontend` -> `PASS`.
2. `npx vitest run tests/unit/messagesV3.phase10.test.tsx tests/unit/MessagesV3.test.tsx tests/unit/messagesV3.profiling-hooks.test.tsx tests/unit/messagesV3.utils.test.ts` -> `PASS`.
3. `npm run check:render_freeze` -> `PASS`.
4. candidate-backed evidence source scripts (`phase10_long_thread_open_scenario.py`, `phase10_scroll_smoothness_profile.py`, `phase10_virtualization_anchor_tests.py`) -> `PASS`.
5. candidate-backed gate aggregation (`phase10_gate_report.py`) -> `PASS`.

## Exit Gates (P10) Status

Gate targets come from `docs/render/system-freeze/phase-gates-v1.json`.

| Gate | Metric | Target | Current value | Status |
|---|---|---|---|---|
| P10-G1 | long_thread_open_tti_p95_ms | `<= 2000` | `1812.4` | pass |
| P10-G2 | scroll_jank_frames_pct | `<= 3` | `1.807` | pass |
| P10-G3 | anchor_break_incidents | `<= 0` | `0.0` | pass |

Required evidence files for closure:

- `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/long_thread_open_scenario.json`
- `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/scroll_smoothness_profile.json`
- `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/virtualization_anchor_tests.json`
- `docs/render/phases/phase-10-progressive-virtualized-rendering/evidence/phase10-gate-report.json`

## Handoff to Phase 11

With base list performance and anchor safety stabilized, Phase 11 can focus on heavy compute off-main-thread optimizations (D05, D06, D07) without changing feed semantics.

Handoff and closeout artifacts:

- `close-phase-v1.md`
- `handoff-to-phase-11.md`

## Effort Estimate

- Size: Large
- Estimated duration: 6-8 engineering days
- Suggested staffing: 1 frontend primary + 1 frontend support
- Confidence level: Medium (depends on current code-path complexity and test debt)
