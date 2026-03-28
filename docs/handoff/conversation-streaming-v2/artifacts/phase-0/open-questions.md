# Phase 0 Open Questions

Use this file only for upstream or codebase questions that cannot be resolved from the current repositories or fixture captures.

## Active Questions

1. Does upstream always emit `itemId` for every `item/agentMessage/delta` frame?
   - Why it matters: message patching cannot be canonical without stable item identity.
   - Current status: unresolved.

2. Does `item/completed` for `fileChange` always contain an authoritative final file list?
   - Why it matters: V2 chooses `outputFilesReplace` as the canonical final-file mechanism.
   - Current status: unresolved.

3. For interrupted turns, should the canonical terminal lifecycle be exposed as `turn_failed`, or should the thread return directly to `idle` with only a warning status item?
   - Why it matters: backend lifecycle and frontend working indicator need one terminal policy.
   - Current status: recommendation is `turn_failed` then clear to `idle` after terminal event handling.

## Resolution Rules

- when a question is resolved, move it to a "Resolved Questions" section with date and decision
- if a question forces a spec change, update the active spec first, then update this file
