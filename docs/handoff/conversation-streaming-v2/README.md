# Conversation Streaming V2 Rollout Plan

Status: active rollout handoff. Phases 0 through 5 are completed, and Phase 6 execution plus audit cutover is the next rollout phase.

Primary specs:

- `docs/specs/conversation-streaming-v2.md`
- `docs/specs/type-contracts-v2.md`

Tracking artifacts:

- `docs/handoff/conversation-streaming-v2/progress.yaml`
- `docs/handoff/conversation-streaming-v2/phase-0-contract-freeze.md`
- `docs/handoff/conversation-streaming-v2/phase-1-codex-client-expansion.md`
- `docs/handoff/conversation-streaming-v2/phase-2-backend-core.md`
- `docs/handoff/conversation-streaming-v2/phase-3-consumer-migration.md`
- `docs/handoff/conversation-streaming-v2/phase-4-frontend-v2.md`
- `docs/handoff/conversation-streaming-v2/phase-5-isolated-rehearsal.md`
- `docs/handoff/conversation-streaming-v2/phase-6-execution-audit-cutover.md`
- `docs/handoff/conversation-streaming-v2/phase-7-ask-planning-cutover.md`
- `docs/handoff/conversation-streaming-v2/phase-8-hard-cutover-cleanup.md`
- `docs/handoff/conversation-streaming-v2/artifacts/README.md`

## Locked Architectural Decisions

- backend source of truth is `ThreadSnapshotV2`
- frontend source of truth is canonical `ConversationItem[]`
- UI renders directly from canonical items
- live SSE and reload or resume use the same model
- tool identity is based on upstream typed item id
- `reasoning` is a first-class item
- `userInput` is a first-class item
- resolved user-input events must carry answers
- no migration of legacy data
- legacy pipeline can be deleted after cutover
- audit is a whole-namespace cutover and may not remain partially on V1

## Current Handoff State

- Phase 0 fixture capture is complete with adapter-captured replayable raw-event samples for every required event class
- Phase 1 is completed and verified
- Phase 2 backend core is completed and verified through focused unit plus integration coverage plus fixture replay
- Phase 3 consumer migration and audit-writer migration is completed and verified through focused backend plus integration coverage and code-search evidence
- Phase 4 hidden frontend rollout is completed and the hidden `/chat-v2` breadcrumb surface is now the rehearsal UI for the next phase
- Phase 5 isolated rehearsal is completed; execution and review-rollup can now run through canonical V2 threads behind a server-side rehearsal flag and sandbox-root gate
- Phase 3 leaves two intentional mixed-mode bridges in place: lineage remains registry-first with legacy session mirroring, and audit readiness remains V2-first with explicit temporary V1 fallback
- Phase 4 intentionally keeps one frontend mixed-mode split: conversation transport on `/chat-v2` is V2-only, while detail-state loading and local-review acceptance remain on current detail APIs
- Phase 4 closeout includes a documented waiver for one unrelated legacy `NodeDetailCard` unit-test failure outside the hidden V2 surface
- remaining upstream "always" guarantees are tracked in `artifacts/phase-0/open-questions.md` as non-blocking follow-up questions
- active design source of truth is `docs/specs/conversation-streaming-v2.md`
- phase tracker source of truth is `progress.yaml`
- every implementation PR should map to one primary phase document in this folder

## Migration Shape

Phase order:

1. Phase 0: contract freeze and fixture capture
2. Phase 1: codex client event expansion
3. Phase 2: canonical backend core
4. Phase 3: consumer migration and audit writer migration
5. Phase 4: frontend V2 hidden breadcrumb surface
6. Phase 5: isolated rehearsal for execution and audit bundle
7. Phase 6: production cutover for execution plus audit
8. Phase 7: ask-planning cutover
9. Phase 8: hard cutover and cleanup

Critical dependency chain:

- Phase 0 before all other phases
- Phase 1 before Phase 2 because projector correctness depends on upstream fields
- Phase 2 before Phase 4 because frontend must target a frozen V2 backend contract
- Phase 4 must preserve breadcrumb-shell parity and stale-request guards before Phase 5 rehearsal starts
- Phase 3 and Phase 5 gates must both pass before Phase 6
- Phase 6 before Phase 7 because execution and audit are the first production cutover bundle
- Phase 7 before Phase 8 because the hard cleanup only happens once all thread roles are on V2

## Cross-Phase Rules

- do not reintroduce pair-based message semantics anywhere in V2
- do not let frontend render from `content`, `parts`, or semantic mapping output
- do not let stale snapshot responses or stale SSE payloads mutate the V2 conversation store
- do not let any service mutate thread lifecycle outside `thread_runtime_service`
- do not let any production audit writer keep using V1 append helpers after Phase 5 gate
- do not allow metadata-bearing mutations to bypass `thread.snapshot`
- do not treat raw tool call state as canonical if a typed tool item exists
- do not use live shadow execution on the production workspace during rehearsal

## Required Phase Outputs

Each phase should update:

- its matching phase markdown file
- `progress.yaml`
- the relevant active spec if the contract changed
- verification notes or evidence under `artifacts/`

## Recommended PR Shape

- one primary PR per phase unless the phase is too large and intentionally split
- if a phase is split, each sub-PR must still preserve the exit criteria listed in the phase doc
- do not mark a phase complete until verification and artifact updates are recorded

## Phase 6 Readiness

Phase 5 delivered the server-flagged rehearsal backend needed to move into Phase 6 execution plus audit cutover planning.

Confirmed Phase 5 qualities:

- rehearsal safety is enforced through `PLANNINGTREE_REHEARSAL_WORKSPACE_ROOT`
- `FinishTaskService` can branch into V2 execution conversation without legacy transcript events
- `ReviewService` can branch into V2 rollup conversation without legacy transcript events
- `/chat-v2` remains the supported observation surface for rehearsal
- `fileChange` authoritative final lists converge through `outputFilesReplace`
- workflow-side invalidation events are emitted during rehearsal

Phase 6 may now assume:

- `/chat-v2` is the frontend rehearsal surface
- execution and review-rollup rehearsal paths already exist behind a server flag
- detail-state loading and local-review acceptance remain side-channel by design at this boundary

## Cutover Definition

The V2 cutover point is reached only when:

- execution and audit already run exclusively on V2
- ask-planning has moved to the same canonical model
- frontend main UI reads only the V2 conversation store
- V1 routes are removed or fail fast
- legacy semantic mapping and accumulator code are deleted

## Update Rules

- set `current_phase` in `progress.yaml` when implementation begins
- move phase state through `not_started -> in_progress -> blocked -> completed`
- record blockers in both the phase doc and `progress.yaml`
- update verification notes before marking a phase completed
- keep historical handoff notes in the phase file after a phase lands
