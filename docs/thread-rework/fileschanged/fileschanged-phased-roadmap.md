# FilesChanged Rework Phased Roadmap

Status: planning skeleton for implementation.

Last updated: 2026-04-03.

## 1. Scope and locked decisions

This roadmap assumes the following are frozen:

- target is full migration toward CodexMonitor-style file-change semantics
- rollout starts with execution lane first
- migration applies to new turns only (no retro migration for old turns)
- `changes[]` becomes canonical render source for file-change content
- temporary fallback for legacy `outputFiles` is allowed only during migration phases

## 2. Non-goals

- no rewrite of unrelated thread streaming behavior
- no historical data backfill for already persisted turns
- no ask-lane scope in this track

## 3. CodexMonitor reference behavior (baseline to copy)

Reference intent from CodexMonitor implementation:

- file changes are represented as one tool item with `toolType="fileChange"` and `changes[]`
- each change carries path-level data and optional patch text (`change.diff`)
- UI renders per-file rows from `changes[]` and shows diff from `change.diff`
- streaming deltas can append output text, while completed payload is authoritative for final `changes[]`
- if no final change payload exists yet, UI stays in pending/minimal state instead of synthesizing fake diff stats

## 4. Phase split and effort estimate

Total effort baseline: 100%.

| Phase | Name | Effort % | Primary owners |
|---|---|---:|---|
| 0 | Contract freeze + acceptance matrix | 8% | BE + FE lead |
| 1 | Backend execution contract bridge (`outputFiles` -> `changes[]`) | 16% | BE |
| 2 | Execution runtime diff hydration to per-file patches | 15% | BE |
| 3 | Frontend execution fileChange renderer cutover | 23% | FE |
| 4 | Parity and regression hardening (execution) | 16% | FE + BE + QA |
| 5 | Audit-lane onboarding (optional after execution stable) | 8% | FE + BE |
| 6 | Rollout gate and stabilization | 9% | BE + FE + QA |
| 7 | Hard cleanup and legacy path removal | 5% | BE + FE |

## 5. Detailed phase skeleton

## Phase 0 (8%) - Contract freeze + acceptance matrix

Goals:

- freeze the target file-change contract for execution migration
- define exact acceptance criteria for parity with CodexMonitor behavior

Implementation checklist:

- define canonical shape for file-change presentation model (`changes[]`)
- define transitional compatibility rules from legacy `outputFiles`
- freeze "new turns only" rollout rule
- freeze acceptance matrix (render, stats, expansion, stream updates, completion updates)

Outputs:

- contract addendum in docs
- parity checklist that later phases must satisfy

Exit criteria:

- no open contract ambiguity for backend/frontend implementation

## Phase 1 (16%) - Backend execution contract bridge (`outputFiles` -> `changes[]`)

Goals:

- produce consistent file-change payloads consumable by CodexMonitor-style UI logic
- preserve compatibility while migration is still in progress

Implementation checklist:

- map execution file-change lifecycle to canonical `changes[]`
- keep backward fields during transition if required by existing consumers
- ensure item identity remains stable when `callId` is missing (fallback by `item.id`)
- ensure completed item is authoritative for final file-change payload

Outputs:

- backend emits stable execution file-change model for new turns
- unit coverage for start/delta/completed transitions

Exit criteria:

- execution snapshots for new turns include deterministic file-change payloads

## Phase 2 (15%) - Execution runtime diff hydration to per-file patches

Goals:

- fill real patch text so expanded rows can render line-level content and stats
- remove dependency on path-only file payloads

Implementation checklist:

- hydrate file-change payload from worktree diff against run start sha
- map diff hunks to per-file patch text for each change entry
- preserve existing output text while appending or setting structured diff safely
- verify no-op behavior when structured diff is already present

Outputs:

- execution file-change items carry enough patch content for per-file render
- tests for path matching, fallback behavior, and empty-diff safety

Exit criteria:

- expanded execution file-change rows show real per-file diff content on new turns

## Phase 3 (23%) - Frontend execution fileChange renderer cutover

Goals:

- migrate execution UI rendering to CodexMonitor-style `changes[]` consumption
- keep stable expand/collapse behavior and deterministic + / - stats

Implementation checklist:

- switch renderer primary source to `changes[]` (not path-only `outputFiles`)
- compute file-level and card-level stats from per-file patch text
- keep temporary fallback only for legacy turns that do not carry patch data
- remove/guard debug flows that can trigger render loops

Outputs:

- execution fileChange cards render path, +/- counters, and patch content reliably
- unit tests for single-file and multi-file expand scenarios

Exit criteria:

- no "path-only +0/-0 + empty panel" behavior for new execution turns

## Phase 4 (16%) - Parity and regression hardening (execution)

Goals:

- prove execution behavior is stable and equivalent to target semantics
- lock the model with automated tests before broad rollout

Implementation checklist:

- backend fixture tests for file-change start/delta/completed edge cases
- frontend tests for rendering, expansion, stats, and fallback behavior
- integration tests through execution workflow turn lifecycle
- capture known non-parity and document temporary exceptions

Outputs:

- execution parity report
- green test matrix for file-change scenarios

Exit criteria:

- parity gate passes for execution lane

## Phase 5 (8%) - Audit-lane onboarding (optional after execution stable)

Goals:

- reuse the same model for audit diff/file-change presentation where applicable
- avoid divergence between execution and audit render semantics

Implementation checklist:

- align audit diff-to-fileChange adapter with canonical model
- reuse shared parser/render utilities where safe
- add scoped tests for audit lane rendering

Outputs:

- audit lane uses the same file-change display semantics where intended

Exit criteria:

- audit behavior is aligned or explicitly documented if intentionally different

## Phase 6 (9%) - Rollout gate and stabilization

Goals:

- roll out safely with clear fallback and observability
- keep impact limited to new turns while gate is active

Implementation checklist:

- add/enable rollout gate for execution file-change migration
- stage rollout: internal -> canary -> broader
- monitor metrics:
  - file-change cards with empty patch on new turns
  - render failures in file-change components
  - mismatch rate between file count and rendered rows
- define rollback triggers and fallback path

Outputs:

- rollout runbook and stabilization notes

Exit criteria:

- stabilization window passes without blocking regressions

## Phase 7 (5%) - Hard cleanup and legacy path removal

Goals:

- remove transitional compatibility code no longer needed
- finalize maintainable ownership boundaries

Implementation checklist:

- remove legacy-only heuristics tied to path-only payloads
- remove temporary guards and migration-only feature flags where approved
- finalize docs and ownership notes

Outputs:

- cleanup handoff and final migration closure notes

Exit criteria:

- execution path defaults to migrated model with no operational dependency on legacy renderer

## 6. Recommended staffing split

- Squad A (backend core): Phase 1 + Phase 2
- Squad B (frontend surface): Phase 3 + frontend part of Phase 4
- Squad C (quality + rollout): Phase 4 + Phase 6
- Squad D (closure): Phase 7

## 7. Dependencies and sequencing

1. Phase 0 must complete before coding starts.
2. Phase 1 should land before Phase 3 full cutover.
3. Phase 2 should land before Phase 3 expansion/parity is evaluated.
4. Phase 4 must be green before broad rollout in Phase 6.
5. Phase 7 starts only after rollout stabilization sign-off.

