# Phase 12 - Data Volume and Heavy Content UX

Status: Completed (all P12 gates passed with candidate-backed evidence).

Date: 2026-04-14.

Scope IDs: D08, E01, E02, E03.

Subphase workspace: `./subphases/`.

Frozen preflight artifacts:

1. `preflight-v1.md`
2. `heavy-content-visibility-policy-v1.md`
3. `evidence/baseline-manifest-v1.json`

## Decision Pack Alignment

Decision source: `docs/render/decision-pack-v1.md`.

Model alignment:

- apply data-volume governance after backend canonical event shaping and render hardening
- keep backend semantic ownership and frontend presentation ownership split

Contract focus:

- primary: `C5` Frontend State Contract v1
- secondary: `C4` Durability Contract v1
- no replay/resync contract drift (`C1`, `C2`)

Must-hold decisions:

- semantic coalescing remains backend-owned and canonical
- frontend truncation/collapse remains view policy only
- archived/load-more flow preserves ordering and Phase 10 anchor invariants
- backend pipeline as canonical source of truth for semantic event shaping

## Objective

Stabilize long-thread rendering by bounding active live data, collapsing heavy rows by default, and exposing full payloads on demand without mutating canonical backend content.

## Frozen Defaults (v1)

1. Snapshot bootstrap:
   - `GET /v3/projects/{project_id}/threads/by-id/{thread_id}?node_id=...&live_limit=1000`
2. Scrollback cap hysteresis:
   - `soft_cap=1000`
   - `hard_cap=1200`
   - `trim_target=900`
3. Heavy-row classification:
   - command output heavy when `chars >= 600` or `lines >= 12`
   - diff heavy when `file_count >= 5` or `(summary + patch chars) >= 3000`
   - generic tool heavy when `output chars >= 2000`
   - `userInput`, `status`, `error` are never auto-collapsed
4. Preview policy (view only):
   - `max_chars=1200`
   - `max_lines=60`
   - full content opened via explicit "View full" action
5. Collapse precedence:
   - manual user toggle has highest priority
   - `in_progress` tool/diff rows auto-expand
   - on completion, heavy rows default collapsed if no manual override exists

See: `heavy-content-visibility-policy-v1.md`.

## In Scope

1. D08: default-collapse heavy rows with persisted per-thread expand/collapse state.
2. E01: bound active in-memory live feed and add history pagination API/store flow.
3. E02: preview + full-artifact navigation with canonical content preservation.
4. E03: backend raw-event compactor tuning and deterministic compatibility checks only.

## Out of Scope

1. Observability layer and rollout/safety layer (`F` and `G`) in this wave.
2. Frontend semantic merge/coalescing logic.
3. Replay cursor semantics or event envelope contract changes.

## Implementation Summary

Backend/contract:

1. Added optional `live_limit` to by-id snapshot endpoint.
2. Added optional `historyMeta` on snapshot payload.
3. Added `/history` pagination endpoint with `before_sequence` cursor contract.

Frontend state/UX:

1. Added history pagination state and `loadMoreHistory()`.
2. Applied scrollback hysteresis trim policy on snapshot/event-apply path.
3. Added heavy-row default collapse policy with manual-toggle precedence.
4. Added preview-to-full modal flow (view-only truncation policy).

E03 finalization:

1. Kept compaction boundaries explicit: `item/completed`, `turn/completed`, `item/tool/requestUserInput`, `serverRequest/resolved`, `thread/status/changed`.
2. Added compatibility test proving compacted and non-compacted projection outcomes remain equivalent.

## Quality Gates (P12)

From `docs/render/system-freeze/phase-gates-v1.json`:

1. `P12-G1`:
   - metric: `live_items_exceeds_scrollback_cap_events`
   - target: `<= 0`
   - source: `long_session_volume_tests`
2. `P12-G2`:
   - metric: `heavy_row_default_collapse_accuracy_pct`
   - target: `>= 95`
   - source: `heavy_row_classification_suite`
3. `P12-G3`:
   - metric: `full_artifact_access_failures`
   - target: `<= 0`
   - source: `preview_to_full_navigation_tests`

Gate scripts:

1. `scripts/phase12_long_session_volume_tests.py`
2. `scripts/phase12_heavy_row_classification_suite.py`
3. `scripts/phase12_preview_to_full_navigation_tests.py`
4. `scripts/phase12_gate_report.py`

Evidence root: `./evidence/`.

## Required Phase 12 Docs

1. `preflight-v1.md`
2. `heavy-content-visibility-policy-v1.md`
3. `close-phase-v1.md`
4. `handoff-to-phase-13.md`

## Exit Conditions

1. Snapshot/history contract tests pass.
2. Frontend heavy-row + preview/full behavior tests pass.
3. Compactor compatibility test passes with no semantic divergence.
4. All P12 gate sources are candidate-backed and gate-eligible.
5. `phase12-gate-report.json` reports all gates passing.
