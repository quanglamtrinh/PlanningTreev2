# Phase 3 Code-Search Evidence

This artifact is supporting manual evidence only. The executable guard for this lane now lives in:

- `backend/tests/unit/test_phase3_no_legacy_audit_writer_callsites.py`

## Legacy Immutable Audit Helper

Command:

```powershell
rg -n "append_immutable_audit_record\(" backend/services backend/routes backend/main.py -S
```

Result:

```text
backend/services\execution_gating.py:182:def append_immutable_audit_record(
```

Interpretation:

- the helper definition still exists
- there are no production callsites outside the helper definition itself

## Transcript Consumer Migration

Command:

```powershell
rg -n "build_prompt_messages\(|chat_state_store\.read_session" backend/services/frame_generation_service.py backend/conversation/services/thread_transcript_builder.py -S
```

Observed implementation state:

- `frame_generation_service.py` calls `ThreadTranscriptBuilder.build_prompt_messages(...)`
- `thread_transcript_builder.py` is the only remaining transcript bridge in this lane
- `ask_planning` still reads V1 session messages intentionally during mixed mode
- `audit` and `execution` prompt history are derived from V2 snapshot items

## Registry-First Metadata Wiring

Command:

```powershell
rg -n "ThreadRegistryService|set_thread_registry_service" backend/main.py backend/services/thread_lineage_service.py -S
```

Observed implementation state:

- `backend/main.py` creates `ThreadRegistryService` and injects it into `ThreadLineageService`
- `backend/services/thread_lineage_service.py` writes metadata through the injected registry service and mirrors session metadata for compatibility

## V2 Audit Writer Wiring

Command:

```powershell
rg -n "upsert_system_message\(" backend/services/node_detail_service.py backend/services/review_service.py backend/conversation/services/system_message_writer.py backend/conversation/services/thread_runtime_service.py -S
```

Observed implementation state:

- `NodeDetailService` writes frame and spec audit records via `upsert_system_message(...)`
- `ReviewService` writes accepted rollup packages via `upsert_system_message(...)`
- production app wiring binds `ConversationSystemMessageWriter` to `ThreadRuntimeService`
