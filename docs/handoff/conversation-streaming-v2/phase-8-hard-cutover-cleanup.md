# Phase 8: Hard Cutover and Cleanup

Status: not started.

## Goal

Remove the legacy V1 conversation pipeline so the shipped product only contains the V2 architecture.

## In Scope

- remove or fail-fast V1 routes
- remove V1 transcript store usage
- delete semantic mapper and semantic blocks from the conversation path
- delete legacy part accumulator and obsolete tests

## Out of Scope

- unrelated workflow cleanup
- broader refactors beyond conversation architecture

## Cleanup Targets

- `backend/ai/part_accumulator.py`
- `backend/storage/chat_state_store.py`
- `frontend/src/stores/chat-store.ts`
- `frontend/src/features/breadcrumb/semanticMapper.ts`
- `frontend/src/features/breadcrumb/SemanticBlocks.tsx`
- any V1-only conversation route or client path left as compatibility scaffolding

## Checklist

- remove or fail-fast legacy conversation routes
- remove V1 transcript store from production dependencies
- delete semantic mapper and semantic block render path
- delete remaining pair-based helper logic
- remove legacy tests that only validate V1 behavior
- refresh active docs so they describe the shipped V2 architecture only

## Verification

- targeted backend and frontend regression suite
- code search for deleted legacy paths
- manual smoke for all three thread roles on V2

## Exit Criteria

- no production code reads legacy transcript conversation schema
- no production render path uses content, parts, or semantic mapping
- the repository docs reflect V2 as the shipped model

## Artifacts To Produce

- `artifacts/phase-8/deletion-checklist.md`
- `artifacts/phase-8/final-regression-results.md`
- `artifacts/phase-8/post-cutover-summary.md`
