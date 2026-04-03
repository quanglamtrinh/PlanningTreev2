# Phase 5 Parity Gate Report

Status: pass (all parity gate suites green on 2026-04-03).

Last updated: 2026-04-03.

## 1. Fixture sources

- Shared parity fixtures:
  - `docs/thread-rework/uiux/artifacts/parity-fixtures/execution-audit-v3-parity-fixtures.json`
- Backend parity fixture test:
  - `backend/tests/unit/test_conversation_v3_parity_fixtures.py`
- Frontend parity fixture test:
  - `frontend/tests/unit/messagesV3.parity.golden.test.ts`

## 2. Gate matrix

| Gate | Status | Evidence |
| --- | --- | --- |
| Semantics parity (`review/diff/explore`) | Pass | `test_conversation_v3_projector.py`, `test_conversation_v3_parity_fixtures.py` |
| Interaction parity (grouping/collapse/autoscroll/pinning) | Pass | `MessagesV3.test.tsx`, `messagesV3.parity.golden.test.ts` |
| Plan/User-input parity | Pass | `MessagesV3.test.tsx`, `threadByIdStoreV3.test.ts`, parity fixtures |
| Micro-behavior persistence parity | Pass | `messagesV3.viewState.test.ts` |
| Safety gate (flags OFF keeps V2, ask unaffected) | Pass | `BreadcrumbChatViewV2.v3-flag.integration.test.tsx` |

## 3. Command set

Backend:

```bash
python -m pytest backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/unit/test_conversation_v3_parity_fixtures.py backend/tests/integration/test_chat_v3_api_execution_audit.py
```

Frontend:

```bash
node frontend/node_modules/vitest/vitest.mjs run tests/unit/messagesV3.utils.test.ts tests/unit/messagesV3.viewState.test.ts tests/unit/MessagesV3.test.tsx tests/unit/threadByIdStoreV3.test.ts tests/unit/messagesV3.parity.golden.test.ts tests/unit/BreadcrumbChatViewV2.v3-flag.integration.test.tsx tests/unit/surfaceRouting.v3-lane-flags.test.ts tests/unit/ConversationMarkdown.desktop-hooks.test.tsx tests/unit/MessagesV3ErrorBoundary.test.tsx --config vitest.config.ts --root frontend --pool=threads --poolOptions.threads.singleThread=true
```

## 4. Divergence log

Current blocking divergences: none recorded in this artifact.

If any test fails, add:

- scenario id
- expected vs actual summary
- severity (`blocking` or `non-blocking`)
- owner and ETA

## 5. Run evidence (2026-04-03)

- Backend:
  - `python -m pytest backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_fixture_replay.py backend/tests/unit/test_conversation_v3_parity_fixtures.py backend/tests/integration/test_chat_v3_api_execution_audit.py`
  - Result: `13 passed`
- Frontend:
  - `node frontend/node_modules/vitest/vitest.mjs run tests/unit/messagesV3.utils.test.ts tests/unit/messagesV3.viewState.test.ts tests/unit/MessagesV3.test.tsx tests/unit/threadByIdStoreV3.test.ts tests/unit/messagesV3.parity.golden.test.ts tests/unit/BreadcrumbChatViewV2.v3-flag.integration.test.tsx tests/unit/surfaceRouting.v3-lane-flags.test.ts tests/unit/ConversationMarkdown.desktop-hooks.test.tsx tests/unit/MessagesV3ErrorBoundary.test.tsx --config vitest.config.ts --root frontend --pool=threads --poolOptions.threads.singleThread=true`
  - Result: `9 files passed, 27 tests passed`

## 6. Release recommendation

- Decision: `Proceed`
- Rationale: all gate rows pass and no blocking divergence remains in semantics/interaction/plan-user-input/safety.
