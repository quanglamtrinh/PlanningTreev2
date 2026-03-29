# Phase 6 Smoke Results

Status: pending.

Record staging or production-like smoke here after enabling `PLANNINGTREE_EXECUTION_AUDIT_V2_ENABLED`.

Suggested checks:

- finish task on a task node produces V2 execution transcript only
- auto-review writes to the task node audit V2 snapshot only
- review rollup writes to the review node audit V2 snapshot only
- `/chat?thread=execution` redirects to `/chat-v2?thread=execution`
- `/chat?thread=audit` redirects to `/chat-v2?thread=audit`
- `/chat-v2?thread=ask` redirects to `/chat?thread=ask`
- workflow detail refresh still updates execution or review state
- no legacy audit or execution transcript events appear on production V2 paths
