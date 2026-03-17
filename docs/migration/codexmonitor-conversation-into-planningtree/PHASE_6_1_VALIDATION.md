# Phase 6.1 Validation

## Current Status
- Complete

## Validation Commands
- `npm test -- src/test/phase6_1DenseEventValidation.test.ts src/utils/threadItems.test.ts src/features/messages/utils/messageRenderUtils.test.ts src/features/threads/hooks/threadReducer/threadItemsSlice.test.ts src/features/app/hooks/useAppServerEvents.test.tsx src/services/events.test.ts`
- `npm run typecheck`
- `npx vite-node --script scripts/phase6_1_dense_event_benchmark.ts --format markdown`

## Gate Checklist
- [x] `P6.1-G1` baseline evidence is recorded for all scoped path classes
- [x] `P6.1-G2` dense-event corpus and expected semantic outcomes are locked
- [x] `P6.1-G3` event-ingress optimizations land with no semantic drift
- [x] `P6.1-G4` reducer and normalization optimizations land with no semantic drift
- [x] `P6.1-G5` render-path optimizations land with no semantic drift
- [x] `P6.1-G6` end-to-end dense-event validation passes on optimized paths

## Environment
- Node: `v22.17.0`
- Platform: `win32`
- Arch: `x64`
- Captured at: `2026-03-17T19:06:23Z`

## Baseline And Optimized Evidence

| Scenario | Path class | Variant | Iterations | Avg ms | Min ms | Max ms | Notes |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| `resume_overlap_dense` | snapshot load and hydrate | baseline | 160 | 0.01 | 0.01 | 0.43 | legacy multi-pass hydrate reference |
| `resume_overlap_dense` | snapshot load and hydrate | optimized | 160 | 0.01 | 0.01 | 0.61 | single-pass `buildThreadHydrationData(...)`; measured cost stays negligible |
| `request_churn_dense` | live event fanout and parsing | baseline | 400 | 0.14 | 0.02 | 3.20 | legacy route reference |
| `request_churn_dense` | live event fanout and parsing | optimized | 400 | 0.14 | 0.03 | 4.30 | routed through `parseAppServerEvent(...)` + `routeAppServerEvent(...)`; no material hotspot remained after measurement |
| `assistant_delta_dense` | reducer state application | current | 40 | 1.64 | 0.57 | 10.05 | dense reducer path stays under the locked corpus with no semantic drift |
| `mixed_long_transcript` | normalization and merge | baseline | 240 | 0.39 | 0.15 | 5.53 | legacy overlap merge reference |
| `mixed_long_transcript` | normalization and merge | optimized | 240 | 0.09 | 0.03 | 2.67 | `mergeThreadItems(...)` map-based overlap lookup |
| `history_limit_dense` | normalization and merge | current | 80 | 0.88 | 0.31 | 3.57 | long-history limit and truncation path |
| `mixed_long_transcript` | transcript render for long mixed conversations | baseline | 120 | 0.26 | 0.11 | 2.07 | legacy visible-item derivation reference |
| `mixed_long_transcript` | transcript render for long mixed conversations | optimized | 120 | 0.20 | 0.07 | 2.41 | `deriveVisibleMessageState(...)` + grouped render path |

## Dense-Event Corpus
- [x] `assistant_delta_dense`
- [x] `reasoning_summary_dense`
- [x] `reasoning_content_dense`
- [x] `plan_delta_dense`
- [x] `tool_output_dense`
- [x] `request_churn_dense`
- [x] `mixed_long_transcript`
- [x] `resume_overlap_dense`
- [x] `history_limit_dense`

## Semantic Equivalence Checks
- [x] item ordering stays stable
- [x] duplicate-upsert behavior stays correct
- [x] review grouping behavior stays unchanged
- [x] plan grouping behavior stays unchanged
- [x] tool output truncation behavior stays unchanged
- [x] reasoning summary boundary behavior stays unchanged
- [x] thread rename and preview side effects stay unchanged where already defined
- [x] rendered transcript meaning matches the baseline path

## Scenario Groups
- [x] high-frequency live stream application is validated
- [x] long snapshot hydrate is validated
- [x] long mixed transcript render is validated
- [x] repeated partial updates to the same item are validated
- [x] overlap between resumed remote items and local items is validated

## Notes
- The locked corpus lives under `src/test/phase6_1DenseEventCorpus.ts` and is consumed by the benchmark harness, targeted regression tests, and the end-to-end dense-event validation runner.
- Snapshot hydrate and live event routing both measured as cheap on the current migrated path. Phase 6.1 therefore closes them with evidence and semantic proof rather than forcing more speculative churn.
- The normalization-and-merge hotspot remained material under dense overlap and now shows a clear measured improvement on the optimized path.
