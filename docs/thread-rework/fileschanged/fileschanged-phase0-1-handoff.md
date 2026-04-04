# FilesChanged Rework - Phase 0-1 Handoff (Planning Skeleton)

Status: planning skeleton.

Date: 2026-04-03.

Owner scope: contract freeze and backend bridge for execution file-change migration.

## 1. Goal and boundary recap

Phase 0 target:

- freeze contract and acceptance matrix for CodexMonitor-style file-change behavior

Phase 1 target:

- land backend bridge so new execution turns can expose canonical `changes[]` data safely

Out of scope for this handoff:

- frontend renderer cutover
- rollout gate enablement
- historical turn backfill

## 2. Locked assumptions

- migration starts with execution lane
- only new turns use migrated model
- legacy turns remain readable via temporary fallback

## 3. Implementation checklist

- [ ] finalize file-change contract addendum (`changes[]` canonical and transition policy)
- [ ] document accepted lifecycle mapping (`item/started`, output delta, `item/completed`)
- [ ] implement backend bridge for new execution turns
- [ ] preserve stable item identity when `callId` is missing
- [ ] add backend unit tests for start/delta/completed merge behavior
- [ ] add contract fixtures for regression verification

## 4. Expected write scope (planned)

- `backend/conversation/domain/*` (types/contract updates)
- `backend/conversation/projector/*` (mapping/patch behavior)
- `backend/conversation/services/*` (runtime/event handling bridge)
- `backend/tests/unit/*` (contract and projector tests)
- `docs/thread-rework/fileschanged/*` (contract notes and acceptance matrix)

## 5. Acceptance evidence expected before closing Phase 0-1

- [ ] snapshot for new execution turn contains canonical file-change payload shape
- [ ] completed payload updates are authoritative over preview state
- [ ] tests cover missing-`callId` fallback and no-regression merge semantics
- [ ] no execution lane regressions in existing thread snapshot reads

## 6. Risks to watch

- dual-shape payload drift (`outputFiles` and `changes[]` disagree)
- merge order bugs when deltas and completed payload race
- accidental breakage for existing consumers still reading `outputFiles`

