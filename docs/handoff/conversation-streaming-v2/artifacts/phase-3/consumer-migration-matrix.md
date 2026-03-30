# Phase 3 Consumer Migration Matrix

## Scope Summary

This phase migrated the remaining critical backend consumers that still depended on V1 transcript or audit-record persistence onto V2-backed abstractions, while preserving mixed-mode behavior for `ask_planning`.

## Consumer Matrix

| Area | Target | Phase 3 outcome | Notes |
| --- | --- | --- | --- |
| Transcript | `backend/services/frame_generation_service.py` | migrated | Uses `ThreadTranscriptBuilder.build_prompt_messages(...)` instead of reading session messages directly |
| Transcript facade | `backend/conversation/services/thread_transcript_builder.py` | expanded | `ask_planning` reads V1; `audit` and `execution` read V2 snapshot items |
| Audit readiness | `backend/services/execution_gating.py` | migrated | Checks canonical V2 audit item ids first, keeps temporary V1 fallback in helper |
| Audit writer | `backend/services/node_detail_service.py` frame confirm | migrated | Writes `audit-record:frame` via `ConversationSystemMessageWriter` |
| Audit writer | `backend/services/node_detail_service.py` spec confirm | migrated | Writes `audit-record:spec` via `ConversationSystemMessageWriter` |
| Audit writer | `backend/services/review_service.py` rollup accept | migrated | Writes `audit-package:rollup` via `ConversationSystemMessageWriter` |
| Metadata facade | `backend/services/thread_lineage_service.py` | migrated | Writes lineage metadata registry-first and mirrors legacy session metadata |
| Metadata callers | `clarify_generation_service.py` | unchanged caller API | Continues to use `ThreadLineageService` facade |
| Metadata callers | `spec_generation_service.py` | unchanged caller API | Continues to use `ThreadLineageService` facade |
| Metadata callers | `split_service.py` | unchanged caller API | Continues to use `ThreadLineageService` facade |
| Metadata callers | `chat_service.py` / `review_service.py` / `finish_task_service.py` | unchanged caller API | Continue using lineage facade while registry becomes authoritative write path |

## Mixed-Mode Notes

- `ask_planning` transcript remains V1-backed in Phase 3, but only behind `ThreadTranscriptBuilder`
- `audit` and `execution` transcript consumers now derive prompt history from V2 snapshot items
- legacy session metadata is still mirrored for compatibility, but registry is the first metadata write target
