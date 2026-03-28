# Phase 0 Open Questions

Use this file only for upstream or codebase questions that cannot be resolved from the current repositories or fixture captures.

## Active Questions

1. Does upstream always emit `itemId` for every `item/agentMessage/delta` frame?
   - Why it matters: message patching cannot be canonical without stable item identity.
   - Current status: non-blocking. The adapter-captured corpus now includes a positive sample with `itemId`, and the V2 projector still fails fast if a future payload omits it.

2. Does `item/completed` for `fileChange` always contain an authoritative final file list?
   - Why it matters: V2 chooses `outputFilesReplace` as the canonical final-file mechanism.
   - Current status: non-blocking. The adapter-captured corpus includes a positive sample with an authoritative final list, and the projector preserves preview file state if a future completed payload omits that list.

## Resolved Questions

1. For interrupted turns, should the canonical terminal lifecycle be exposed as `turn_failed`, or should the thread return directly to `idle` with only a warning status item?
   - Resolved on 2026-03-28.
   - Decision: emit `turn_failed` as the terminal lifecycle, then clear the thread back to `idle` after terminal handling.

## Resolution Rules

- when a question is resolved, move it to a "Resolved Questions" section with date and decision
- if a question forces a spec change, update the active spec first, then update this file
