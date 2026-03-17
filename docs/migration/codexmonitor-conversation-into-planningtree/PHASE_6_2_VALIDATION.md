# Phase 6.2 Validation

## Current Status
- Complete

## Validation Commands And Results
- frontend unit proof:
  - `npm run test:unit -- execution-conversation-stream.test.tsx planning-conversation-stream.test.tsx ask-conversation-stream.test.tsx conversation-store.test.ts applyConversationEvent.test.ts ConversationSurface.test.tsx useConversationRequests.test.ts conversation-recovery-orchestration.test.tsx`
  - result: passed, `28` test files and `192` tests green on `2026-03-17`
- frontend typecheck:
  - `npm run typecheck`
  - result: passed
- frontend build:
  - `npm run build`
  - result: passed
- backend proof:
  - `python -m pytest backend/tests/unit/test_conversation_gateway.py backend/tests/unit/test_conversation_broker.py backend/tests/unit/test_conversation_store.py backend/tests/integration/test_conversation_gateway_api.py`
  - result: passed, `55` tests green on `2026-03-17`

## Gate Checklist
- [x] `P6.2-G1` the PlanningTreeMain-native concurrency and replay matrix is recorded
- [x] `P6.2-G2` isolation is proven across scope, stream, turn, and request boundaries
- [x] `P6.2-G3` reconnect behavior is sequence-safe and stale-safe
- [x] `P6.2-G4` guarded refresh is recovery-only and durable-first
- [x] `P6.2-G5` refresh, reload, and restart replay reconstruct the same semantic state as the live path
- [x] `P6.2-G6` targeted validation, typecheck, build, backend pytest, and docs all agree on closeout

## Canonical Validation Matrix
| Trigger or scenario | Durable source of truth | Expected live behavior | Forbidden failure mode | Proving surface |
| --- | --- | --- | --- | --- |
| wrong `project_id/node_id/thread_type` scope | scope-keyed canonical conversation snapshot | ignore event or refresh result for the current mounted scope | active scope mutates from another scope's event or refresh | `frontend/tests/unit/conversation-store.test.ts`, `frontend/tests/unit/ask-conversation-stream.test.tsx` |
| wrong `conversation_id` | current durable snapshot for the mounted scope | ignore event for another conversation | current conversation mutates from another conversation's event | `frontend/src/features/conversation/model/applyConversationEvent.ts`, `frontend/tests/unit/conversation-store.test.ts` |
| stale `event_seq` or duplicate replay | current durable `event_seq` in store | no-op | accepted live state regresses | `frontend/tests/unit/conversation-store.test.ts`, `frontend/tests/unit/execution-conversation-stream.test.tsx`, `frontend/tests/unit/ask-conversation-stream.test.tsx` |
| gapful `event_seq` | durable snapshot plus guarded recovery | do not synthesize locally; trigger recovery | local state invents missing events or drifts across reconnect | `frontend/tests/unit/applyConversationEvent.test.ts`, `frontend/tests/unit/conversation-store.test.ts`, `frontend/tests/unit/execution-conversation-stream.test.tsx`, `frontend/tests/unit/planning-conversation-stream.test.tsx` |
| wrong or stale `stream_id` | current `active_stream_id` | ignore stale or non-owning stream events | stale stream mutates active conversation state | `frontend/tests/unit/conversation-store.test.ts`, `frontend/tests/unit/execution-conversation-stream.test.tsx`, `backend/tests/integration/test_conversation_gateway_api.py` |
| terminal close followed by stale stream emission | durable terminal snapshot with cleared ownership | ignore stale emission after terminalization or remount | stale stream revives ownership after close | `backend/tests/unit/test_conversation_gateway.py`, `frontend/tests/unit/conversation-recovery-orchestration.test.tsx` |
| same `conversation_id` rebased with newer `active_stream_id` | refreshed durable snapshot and current bootstrap generation | only the current generation may continue streaming | older reconnect or older stream completion revives superseded ownership | `frontend/tests/unit/execution-conversation-stream.test.tsx`, `frontend/tests/unit/ask-conversation-stream.test.tsx` |
| stale `turn_id` completion or request resolution | active-turn ownership in the current conversation | stale terminal or request-resolution event is a no-op | older turn clears or resolves newer active-turn state | `frontend/tests/unit/applyConversationEvent.test.ts`, `frontend/tests/unit/conversation-store.test.ts` |
| same `request_id` reused in different conversations | `conversation_id + request_id` ownership | keep request state isolated by conversation | cross-conversation dedupe or resolution | `backend/tests/integration/test_conversation_gateway_api.py`, `backend/services/conversation_gateway.py` |
| request resolved after active turn advanced | active-turn ownership plus `conversation_id + request_id` | stale resolution does not mutate pending-request map | stale interactive flow clears current pending request | `frontend/tests/unit/applyConversationEvent.test.ts` |
| manual refresh during reconnect or guarded refresh after terminal completion | refreshed durable snapshot | refresh first, then one allowed reconnect path | refresh becomes a second live authority or reconnect wins before refresh | `frontend/tests/unit/planning-conversation-stream.test.tsx`, `frontend/tests/unit/execution-conversation-stream.test.tsx` |
| manual refresh while switching scope | current scope key and current bootstrap generation | older refresh result is ignored after scope switch | old refresh output overwrites newer mounted scope | `frontend/tests/unit/ask-conversation-stream.test.tsx` |
| old EventSource emits after unmount or remount | remounted durable snapshot plus current generation | stale buffered emission is ignored | old stream mutates remounted state | `frontend/tests/unit/conversation-recovery-orchestration.test.tsx`, `frontend/tests/unit/execution-conversation-stream.test.tsx` |
| snapshot baseline older than already accepted live state | latest accepted live `event_seq` in the canonical store | older hydrate result is ignored | refresh regresses newer accepted state | `frontend/tests/unit/conversation-store.test.ts` |
| remount, reload, or restart from durable snapshot | durable snapshot plus accepted events | rebuild the same semantic state as before disconnect | remount-only drift in ordering, status, active stream, active turn, pending requests, or passive/review projections | `frontend/tests/unit/conversation-recovery-orchestration.test.tsx`, `frontend/tests/unit/ConversationSurface.test.tsx`, `backend/tests/unit/test_conversation_gateway.py`, `backend/tests/unit/test_conversation_store.py` |
| publish across project and conversation boundaries | project and conversation keyed broker channels | events stay isolated to the owning conversation stream | broker leak across conversations | `backend/tests/unit/test_conversation_broker.py` |

## Proving Surfaces
- frontend:
  - `frontend/tests/unit/applyConversationEvent.test.ts`
  - `frontend/tests/unit/conversation-store.test.ts`
  - `frontend/tests/unit/execution-conversation-stream.test.tsx`
  - `frontend/tests/unit/planning-conversation-stream.test.tsx`
  - `frontend/tests/unit/ask-conversation-stream.test.tsx`
  - `frontend/tests/unit/ConversationSurface.test.tsx`
  - `frontend/tests/unit/useConversationRequests.test.ts`
  - `frontend/tests/unit/conversation-recovery-orchestration.test.tsx`
- backend:
  - `backend/tests/unit/test_conversation_gateway.py`
  - `backend/tests/unit/test_conversation_broker.py`
  - `backend/tests/unit/test_conversation_store.py`
  - `backend/tests/integration/test_conversation_gateway_api.py`

## Notes
- The frontend unit command runs the broader `tests/unit` directory because of the current `test:unit` script shape. That broader run still emits pre-existing React `act(...)` warnings in older tests, but the proof suite passed and no new 6.2 assertion failed.
- The production build reports a chunk-size advisory warning only; it is not a 6.2 blocker.
