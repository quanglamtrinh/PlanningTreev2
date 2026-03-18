# Phase 6.1 Plan: Performance And Dense-Event Hardening

## Inheritance
- This subphase inherits all Phase 6 entry conditions, invariants, gate rules, and cleanup boundaries from `PHASE_6_PLAN.md`.
- It narrows Phase 6 to performance and dense-event hardening only.

## Summary
- Phase 6.1 is the first hardening subphase under Phase 6.
- It improves hot-path and dense-event performance on the migrated conversation-v2 platform without changing semantics, ownership, terminal-state behavior, or replay authority.
- This subphase is complete only when:
  - baseline evidence exists for the scoped migrated path categories
  - dense-event fixtures and expected semantic outcomes are locked
  - confirmed hotspots are optimized
  - the optimized path remains semantically equivalent to baseline behavior

Default artifacts to maintain during this subphase:
- `PHASE_6_1_PLAN.md`
- `PHASE_6_1_PROGRESS.md`
- `PHASE_6_1_VALIDATION.md`
- `PHASE_6_1_OPEN_ISSUES.md`
- `PHASE_6_BATCHES.md`
- `PHASE_6_CHANGELOG.md`

## Gate Model
Use the umbrella invariants as fixed constraints and define the concrete 6.1 gates up front.

Gates:
- `P6.1-G1` - baseline evidence captured for all scoped path classes
- `P6.1-G2` - dense-event corpus and expected semantic outcomes locked
- `P6.1-G3` - event-ingress optimizations land with no semantic drift
- `P6.1-G4` - reducer and normalization optimizations land with no semantic drift
- `P6.1-G5` - render-path optimizations land with no semantic drift
- `P6.1-G6` - end-to-end dense-event validation passes on optimized paths

Baseline path classes:
- snapshot load and hydrate
- live event fanout and parsing
- reducer state application
- normalization and merge paths
- transcript render for long mixed conversations

Recorded baseline evidence must include:
- path class
- scenario name
- command or harness used
- environment notes
- before and after tables when optimization lands
- semantic validation reference

Rule:
- relative improvement claims without recorded same-path baseline evidence are insufficient

## Source Context Anchors And Hotspot Hints
Use CodexMonitor source context only as comparative hotspot input.

Primary comparative anchors:
- `docs/codebase-map.md`
- `docs/app-server-events.md`
- `src/services/events.ts`
- `src/features/app/hooks/useAppServerEvents.ts`
- `src/features/threads/hooks/useThreadsReducer.ts`
- `src/features/threads/hooks/threadReducer/threadItemsSlice.ts`
- `src/utils/threadItems.ts`
- `src/features/messages/components/Messages.tsx`

Likely hotspot categories to confirm during `P6.1.a`:
- single-listener event fanout and listener dispatch
- app-server event parsing and routing overhead
- repeated `prepareThreadItems(...)` and `normalizeItem(...)` work on each delta
- repeated merge and upsert behavior on long transcripts
- render-time derivation for long mixed transcripts with tool, reasoning, review, and request content

These are starting hypotheses only. `P6.1.a` must confirm actual hotspots before optimization work is claimed.

## Dense-Event Corpus
Create a fixed dense-event test corpus and treat it as the semantic ground truth for Phase 6.1.

Corpus classes:
- repeated assistant deltas
- repeated reasoning summary deltas
- repeated reasoning content deltas
- repeated plan deltas
- repeated tool output updates
- request, approval, and user-input churn
- long mixed transcripts containing passive, interactive, and lineage-bearing items
- resume and merge scenarios with local plus remote overlap
- long transcripts that trigger item preparation limits and summarization logic

Expected semantic checks for the corpus:
- item ordering stays stable
- duplicate-upsert behavior stays correct
- review and plan grouping behavior stays unchanged
- tool output truncation behavior stays unchanged
- reasoning summary boundary behavior stays unchanged
- thread rename and preview side effects stay unchanged where already defined
- rendered transcript meaning matches the baseline path

Rule:
- no optimization work starts until the corpus and expected outcomes are documented and linked from validation artifacts

## Bounded Implementation Batches
### `P6.1.a - Baseline capture and hotspot inventory`
- measure the scoped path classes
- identify actual hotspots instead of pre-optimizing by guess
- record the initial gate evidence for `P6.1-G1`
- produce:
  - baseline table by path class
  - environment notes
  - scenario list for later comparison
  - hotspot inventory prioritized by confirmed cost

### `P6.1.b - Event ingress and reducer hardening`
- target event fanout and parse overhead first
- target repeated reducer work next, especially paths that repeatedly call normalization or preparation on each delta
- keep reducer semantics identical under dense streams
- comparison anchors:
  - `src/services/events.ts`
  - `src/features/app/hooks/useAppServerEvents.ts`
  - `src/features/threads/hooks/useThreadsReducer.ts`
  - `src/features/threads/hooks/threadReducer/threadItemsSlice.ts`
  - `src/utils/threadItems.ts`

### `P6.1.c - Render and long-transcript hardening`
- target render-model and transcript rendering costs only after event and reducer hotspots are understood
- optimize long-transcript rendering, grouping, expansion state, and derived render metadata
- any virtualization or deferred rendering is allowed only if semantic output and user-visible ordering remain equivalent
- comparison anchors:
  - `src/features/messages/components/Messages.tsx`
  - `src/features/messages/utils/messageRenderUtils.ts`
  - `src/utils/threadItems.ts`

Optimization rules:
- no public semantic contract changes
- no replay-authority changes
- no batching, memoization, truncation, or virtualization that changes semantic outcome
- no cleanup or removal work in 6.1

## Interface Impact
Expected interface impact for 6.1:
- no new product semantics
- no new public conversation APIs by default
- no cleanup or removal interfaces

Allowed additions:
- internal benchmark or profiling helpers
- dev or test-only counters or instrumentation hooks
- fixture inputs and measurement docs
- validation helpers used to compare baseline vs optimized semantic output

Default rule:
- any added instrumentation must be internal or dev/test-only and must not become a production semantic dependency

## Test Plan
Performance and dense-event validation must cover:
- baseline and optimized timings for each scoped path class
- repeated delta application on long transcripts
- mixed passive, interactive, and lineage-bearing transcript preparation
- resume and merge behavior with local and remote overlap
- transcript rendering with plan blocks, reasoning, tool groups, request blocks, and long histories
- max-item limiting and summarization behavior under long histories
- semantic equivalence between baseline and optimized outputs for the dense-event corpus

Required scenario groups:
- high-frequency live stream application
- long snapshot hydrate
- long mixed transcript render
- repeated partial updates to the same item
- overlap between resumed remote items and existing local items

Validation passes only when:
- `P6.1-G1` through `P6.1-G6` are all satisfied
- no semantic drift is observed in the locked corpus
- improvement claims are backed by recorded before/after evidence on the same path class

## Assumptions And Defaults
- This plan inherits all Phase 6 umbrella invariants unchanged.
- CodexMonitor source files are comparative hotspot references only, not implementation requirements for PlanningTree.
- 6.1 is not allowed to absorb cleanup work from 6.3 or robustness work from 6.2 except where a measurement harness is needed to prove semantic equivalence.
- If a potential optimization cannot preserve semantic equivalence clearly, it is deferred rather than forced into Phase 6.1.
