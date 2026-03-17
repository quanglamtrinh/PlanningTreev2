# Phase 6.1 Open Issues

## Current Status
- No open Phase 6.1 blockers remain.

## Resolved During Closeout

| Issue ID | Title | Previous classification | Resolution status |
| --- | --- | --- | --- |
| `P6-OI-001` | Baseline performance evidence not yet recorded | Blocking for `P6.1-G1` and any improvement claim | Resolved on `2026-03-17` |
| `P6-OI-002` | Dense-event corpus and thresholds not yet locked | Blocking for `P6.1-G2` and any optimization claim | Resolved on `2026-03-17` |

## Resolution Notes

### `P6-OI-001` - Resolved
- same-path benchmark evidence now exists in `PHASE_6_1_VALIDATION.md`
- the recorded evidence covers all five scoped path classes

### `P6-OI-002` - Resolved
- the locked corpus now lives in `src/test/phase6_1DenseEventCorpus.ts`
- the corpus is reused by:
  - `scripts/phase6_1_dense_event_benchmark.ts`
  - targeted regression suites
  - `src/test/phase6_1DenseEventValidation.test.ts`

## Notes
- Any new performance issue discovered later should be tracked as a fresh Phase 6 issue, not as a reopened Phase 6.1 gate blocker unless it invalidates the recorded evidence directly.
