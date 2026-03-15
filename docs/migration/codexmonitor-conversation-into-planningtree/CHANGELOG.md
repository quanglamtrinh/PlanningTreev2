# Migration Changelog

## 2026-03-14
- Formalized Plan 1 into the authoritative master plan.
- Added the full migration artifact set under `docs/migration/codexmonitor-conversation-into-planningtree/`.
- Added backend and frontend Phase 1 foundation scaffolding for:
  - canonical conversation identity
  - runtime mode separation
  - normalized rich message schema
  - keyed frontend conversation state
  - dedicated backend conversation persistence contracts
- Compatibility notes:
  - existing chat and ask paths remain in place
  - new conversation foundations are additive only in this batch
- Deferred:
  - thin gateway implementation
  - session manager implementation
  - visible conversation UI cutover
- Verification:
  - `python -m pytest backend/tests/unit/test_conversation_store.py`
  - `npm run test:unit -- conversation-store.test.ts`
  - `npm run build`
