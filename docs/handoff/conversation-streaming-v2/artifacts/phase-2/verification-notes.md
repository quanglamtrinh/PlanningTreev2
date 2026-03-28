# Phase 2 Verification Notes

Date: 2026-03-28

## Commands Run

```powershell
python -m py_compile `
  backend/conversation/domain/events.py `
  backend/conversation/domain/types.py `
  backend/conversation/projector/thread_event_projector.py `
  backend/conversation/services/request_ledger_service.py `
  backend/conversation/services/thread_query_service.py `
  backend/conversation/services/thread_registry_service.py `
  backend/conversation/services/thread_runtime_service.py `
  backend/conversation/services/thread_transcript_builder.py `
  backend/conversation/services/workflow_event_publisher.py `
  backend/conversation/storage/thread_registry_store.py `
  backend/conversation/storage/thread_snapshot_store_v2.py `
  backend/routes/chat_v2.py `
  backend/main.py `
  backend/storage/storage.py

python -m pytest `
  backend/tests/unit/test_conversation_v2_stores.py `
  backend/tests/unit/test_conversation_v2_projector.py `
  backend/tests/unit/test_conversation_v2_fixture_replay.py `
  backend/tests/integration/test_chat_v2_api.py `
  -q
```

## Result

- syntax check passed
- focused Phase 2 pytest suite passed: `16 passed in 7.18s`

## Verified Behaviors

- V2 snapshot store and registry store round-trip successfully
- projector rejects missing-item patch mismatches
- projector treats `outputFilesReplace` as authoritative over preview `outputFilesAppend`
- `/v2` snapshot route returns wrapped `ok/data`
- `/v2` thread stream emits first-frame `thread.snapshot`
- `/v2` start-turn path persists canonical user item and background raw events
- invalid `after_snapshot_version` returns wrapped `conversation_stream_mismatch`
- `/v2` resolve-user-input updates both canonical item state and the persisted pending request ledger
- ensure-and-read metadata repair publishes a fresh `thread.snapshot`
- `/v2` reset emits `thread.reset` followed by a fresh `thread.snapshot`
- workflow V2 route streams wrapped workflow envelopes from the dedicated V2 broker
- Phase 0 adapter-captured raw corpus replays deterministically through the pure projector
- no spec drift was observed between the replay corpus and the frozen V2 contract

## Remaining Phase 2 Verification Gaps

- no blocking Phase 2 verification gaps remain
- upstream "always" guarantees tracked in `artifacts/phase-0/open-questions.md` are non-blocking follow-up questions rather than Phase 2 blockers
