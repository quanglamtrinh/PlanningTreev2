# Ask Thread V3 - Phase 2-3 Handoff (Implemented)

Status: implemented.

Date: 2026-04-03.

Owner scope: backend runtime/policy guard for ask lane (Phase 2) and frontend ask lane V3 cutover + metadata shell parity (Phase 3).

## 1. Goal and boundary recap

This handoff confirms delivery of:

- Phase 2 objective (12%): strict ask read-only runtime guard and workflow artifact write-scope enforcement.
- Phase 3 objective (20%): ask lane UI cutover to V3 shared by-id route and metadata shell parity.

Out of scope intentionally kept:

- No new ask transcript actions were introduced (plan-actions remain execution-only).
- No CTA move into ask transcript (CTA stays in right node-detail panel).
- No rollout gate wiring changes in this handoff (`ask_v3_backend_enabled`, `ask_v3_frontend_enabled` are deferred to rollout phase).

## 2. Implemented behavior

### 2.1 Ask remains usable post-FinishTask but runtime is always read-only

- Removed ask-specific writable block in `ChatService._check_thread_writable`; audit/execution rules remain unchanged.
- Ask can continue Q&A/clarification after FinishTask.
- Runtime enforcement is now defense-in-depth in `ThreadRuntimeService`:
  - ask turns always call Codex with `writable_roots=None`
  - ask turns always call Codex with `sandbox_profile="read_only"`

### 2.2 Ask turn policy violation handling for file-change output

- Added ask policy check after each ask turn:
  - if turn emits tool item `toolType="fileChange"`, or
  - if tool item has non-empty `outputFiles`,
  - then turn is forced to `failed` with policy error.
- Policy failure message: `Ask lane is read-only. File-change output is not allowed in ask turns.`

### 2.3 Artifact write-scope enforcement for Frame/Clarify/Spec

- Added centralized utility guard: `ensure_allowed_workflow_artifact_write(node_dir, target_path)`.
- Guard allows only direct files under node directory and only this allowlist:
  - `frame.md`, `clarify.json`, `spec.md`
  - `frame.meta.json`, `spec.meta.json`
  - `frame_gen.json`, `clarify_gen.json`, `spec_gen.json`
- Frame/Clarify/Spec services now fail generation job immediately on out-of-scope target path.

### 2.4 Generation runtime now also runs read-only

- `FrameGenerationService`, `ClarifyGenerationService`, `SpecGenerationService` now call `run_turn_streaming` with:
  - `writable_roots=None`
  - `sandbox_profile="read_only"`
- Agent no longer has any writable workspace grant in generation runtime.
- Backend remains the only writer for allowed workflow artifacts after structured parse.

### 2.5 Ask lane frontend cutover to V3 surface

- Ask routing now canonical on `/chat-v2` (shared V3 namespace).
- Legacy ask route `/chat?thread=ask` is redirect-only to `/chat-v2?thread=ask`.
- Ask entry points now navigate to V3 surface:
  - graph breadcrumb open
  - sidebar open
  - legacy breadcrumb route canonicalization

### 2.6 Registry-first ask thread identity and fallback bootstrap

- Workflow state/view now exposes `askThreadId`.
- Backend fills `askThreadId` from Thread Registry (`ask_planning` entry).
- If registry is empty, backend seeds from legacy ask session once, writes registry entry, then returns the seeded id.
- Frontend `BreadcrumbChatViewV2`:
  - maps `ask -> ask_planning`
  - loads ask thread via by-id flow using `askThreadId`
  - one-time fallback bootstrap: call ask V2 snapshot to materialize thread id, then reload workflow state.

### 2.7 Ask metadata shell parity and composer behavior

- Ask shell now renders through metadata prefix (`FrameContextFeedBlock` variant `ask`) on V3 feed.
- Ask shell is decoupled from transcript body actions.
- Ask composer is enabled when snapshot exists and no active turn; no `shaping_frozen` lock on FE side.
- Audit remains read-only in composer/store path.

## 3. Public contract updates

- Backend workflow state now includes `askThreadId`.
- Frontend type `NodeWorkflowView` now includes `askThreadId?: string | null` (backward-compatible field addition).
- Frontend route contract for ask is now canonical V3 surface: `/chat-v2?thread=ask`.

## 4. Acceptance gate status

Phase 2 acceptance:

- No ask turn runs with write-enabled sandbox: satisfied (`read_only` + no writable roots).
- No generation write path outside workflow artifact allowlist: satisfied (central guard integrated in frame/clarify/spec services).

Phase 3 acceptance:

- Ask lane runs on V3 by-id flow: satisfied (route + by-id identity load + store send support for ask).
- Ask metadata shell is stable and transcript-independent: satisfied (prefix render for ask variant).
- Execution/audit behavior preserved: satisfied by regression suite below.

## 5. Test evidence (implementation run)

Backend:

- `python -m pytest backend/tests/unit/test_thread_readonly.py backend/tests/unit/test_workflow_artifact_write_guard.py backend/tests/unit/test_frame_generation_service.py backend/tests/unit/test_clarify_generation_service.py backend/tests/unit/test_spec_generation_service.py -q`
  - Result: `56 passed`
- `python -m pytest backend/tests/integration/test_chat_v2_api.py -q`
  - Result: `15 passed`
- `python -m pytest backend/tests/integration/test_chat_v3_api_execution_audit.py -q`
  - Result: `16 passed`
- `python -m pytest backend/tests/integration/test_workflow_v2_review_thread_context.py -q`
  - Result: `1 passed`

Frontend:

- `npm --prefix frontend run test:unit -- ...`
  - Result: `193 passed`
- `npm --prefix frontend run typecheck`
  - Result: `passed`

## 6. Changed file index (Phase 2-3)

Backend runtime/policy:

- `backend/services/chat_service.py`
- `backend/conversation/services/thread_runtime_service.py`
- `backend/services/workflow_artifact_write_guard.py` (new)
- `backend/services/frame_generation_service.py`
- `backend/services/clarify_generation_service.py`
- `backend/services/spec_generation_service.py`
- `backend/storage/workflow_state_store.py`
- `backend/services/execution_audit_workflow_service.py`

Backend tests:

- `backend/tests/unit/test_thread_readonly.py`
- `backend/tests/unit/test_workflow_artifact_write_guard.py` (new)
- `backend/tests/unit/test_frame_generation_service.py`
- `backend/tests/unit/test_clarify_generation_service.py`
- `backend/tests/unit/test_spec_generation_service.py`
- `backend/tests/integration/test_chat_v2_api.py`
- `backend/tests/integration/test_chat_v3_api_execution_audit.py`

Frontend:

- `frontend/src/features/conversation/surfaceRouting.ts`
- `frontend/src/features/breadcrumb/BreadcrumbChatView.tsx`
- `frontend/src/features/conversation/BreadcrumbChatViewV2.tsx`
- `frontend/src/features/conversation/state/threadByIdStoreV3.ts`
- `frontend/src/features/graph/GraphWorkspace.tsx`
- `frontend/src/features/graph/Sidebar.tsx`
- `frontend/src/api/types.ts`

Frontend tests:

- `frontend/tests/unit/surfaceRouting.v3-lane-flags.test.ts`
- `frontend/tests/unit/BreadcrumbChatView.test.tsx`
- `frontend/tests/unit/BreadcrumbChatViewV2.test.tsx`
- `frontend/tests/unit/BreadcrumbChatViewV2.v3-flag.integration.test.tsx`
- `frontend/tests/unit/GraphWorkspace.test.tsx`
- `frontend/tests/unit/Sidebar.test.tsx`

## 7. Follow-up for next phase

- Phase 4 should wire frame/clarify/spec UI action flow fully on V3 ask lane (generation -> review -> confirm UX).
- Phase 5 should focus on parity hardening and end-to-end regression matrix.
- Rollout gate staged enablement and observability remain in rollout phase (Phase 6).
