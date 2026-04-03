# Ask Thread V3 Planning: Reading Instructions

Date: 2026-04-03

Purpose: use this checklist to read existing docs/code in a deterministic order and produce an implementation plan for migrating ask thread to V3.

## 1. Read order (strict)

1. `docs/thread-rework/uiux/ask-thread-v3-handoff.md`
2. `docs/thread-rework/uiux/execution-audit-hard-cutover.md`
3. `docs/thread-rework/uiux/execution-audit-uiux-parity-blueprint.md`
4. `docs/thread-rework/uiux/phase3-8-handoff.md`
5. `docs/thread-rework/uiux/phase5-8-implementation-plan.md`

## 2. While reading, extract these reusable patterns

- Contract-first sequence:
  - freeze types
  - freeze event names
  - freeze boundaries
- Projector and stream model:
  - snapshot first-frame
  - incremental replay
  - version mismatch recovery
- Frontend model:
  - thread-scoped reducer/store
  - visible-state derivation
  - behavior parity test approach
- Rollout model:
  - parity gate artifact
  - cutover gate
  - rollback runbook

## 3. Code reading map (after docs)

### Frontend ask current path

- `frontend/src/features/breadcrumb/BreadcrumbChatView.tsx`
- `frontend/src/stores/chat-store.ts`
- `frontend/src/features/conversation/surfaceRouting.ts`
- `frontend/src/api/client.ts`

### Frontend V3 reference path

- `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- `frontend/src/features/conversation/components/v3/MessagesV3.tsx`
- `frontend/src/features/conversation/components/v3/messagesV3.utils.ts`

### Backend ask current path

- `backend/routes/chat.py`
- `backend/services/chat_service.py`
- `backend/services/thread_lineage_service.py`

### Backend V3 reference path

- `backend/routes/workflow_v3.py`
- `backend/conversation/projector/thread_event_projector_v3.py`
- `backend/services/execution_audit_workflow_service.py`

## 4. Required outputs before writing plan

- Ask V3 contract draft:
  - snapshot type
  - item type matrix
  - uiSignals type
- Event contract draft:
  - stream event names
  - envelope shape
  - patch semantics
- Migration boundary doc:
  - in scope
  - out of scope
  - compatibility and rollback

## 5. Questions you must answer in the plan

- Will ask V3 reuse `MessagesV3` directly or require ask-specific wrapper sections?
- How will shaping-focused UX (frame/spec context) coexist with V3 feed without behavior regressions?
- Will ask rollout be phased behind gate first or hard cutover directly?
- What is the parity gate suite for ask (semantics, interaction, plan/user-input, micro-behavior, safety)?
- Which existing legacy routes/services can be removed at each phase?

## 6. Plan skeleton template (fill this)

- Phase 0: Ask V3 contract freeze.
- Phase 1: Ask V3 backend foundation (parallel path).
- Phase 2: Ask V3 frontend core wiring.
- Phase 3: Ask behavior parity.
- Phase 4: Ask persistence and UX parity.
- Phase 5: Ask parity verification + gate artifact.
- Phase 6: Ask cutover.
- Phase 7: Cleanup + legacy removal + docs/runbook.

## 7. Acceptance criteria for the final ask migration plan

- Each phase has:
  - explicit scope
  - API/type changes
  - test suites
  - gate criteria
- Plan explicitly protects:
  - execution/audit stability
  - non-ask behavior
  - rollback feasibility
- Plan includes exact artifacts to publish:
  - parity report
  - cutover checklist
  - rollback runbook

