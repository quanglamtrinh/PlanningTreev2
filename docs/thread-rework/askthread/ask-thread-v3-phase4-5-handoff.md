# Ask Thread V3 Phase 4-5 Handoff

Date: 2026-04-03

## Scope locked for this handoff

- Ask lane remains Q&A/read-only only.
- Ask shell stays metadata-driven and independent from ask transcript content.
- CTA stays in node-detail panel (not moved into ask thread).
- Public API surface is unchanged for shaping (`generate/confirm/get-status` node endpoints).
- File writes remain backend-owned and restricted to workflow artifact allowlist.

## Phase 4 completion (Wiring Frame/Clarify/Spec on Ask V3)

Status: PASS

- Added shared ask shell action-state store for `frame/clarify/spec` with `generate/confirm` status.
- Wired node-detail shaping actions to update shared ask shell status in real time.
- Ask shell now renders shaping status from workflow metadata/action-state, not transcript body.
- Ask reset behavior keeps metadata shell/context visible.
- No new write path was introduced from ask lane.

## Phase 5 completion (Parity and regression hardening)

Status: PASS

- Backend safety tests cover ask read-only behavior and artifact write allowlist.
- Frontend parity tests cover ask shell rendering and action-status updates.
- Integration parity tests cover ask/execution/audit lane routing and V3 lane flags.
- Sign-off gate artifact recorded in this file with command evidence below.

## Test command evidence

### Frontend parity suite

Command:

```bash
node frontend/node_modules/vitest/vitest.mjs run \
  tests/unit/BreadcrumbChatView.test.tsx \
  tests/unit/BreadcrumbChatViewV2.test.tsx \
  tests/unit/BreadcrumbChatViewV2.v3-flag.integration.test.tsx \
  tests/unit/FrameContextFeedBlock.test.tsx \
  tests/unit/GraphWorkspace.test.tsx \
  tests/unit/Sidebar.test.tsx \
  tests/unit/surfaceRouting.v3-lane-flags.test.ts \
  tests/unit/NodeDetailCard.test.tsx \
  --config vitest.config.ts --root frontend --pool=threads --poolOptions.threads.singleThread=true
```

Result: `8 passed, 66 passed tests`

### Backend safety/parity suite

Command:

```bash
python -m pytest -q \
  backend/tests/unit/test_thread_readonly.py \
  backend/tests/unit/test_workflow_artifact_write_guard.py \
  backend/tests/unit/test_frame_generation_service.py \
  backend/tests/unit/test_clarify_generation_service.py \
  backend/tests/unit/test_spec_generation_service.py \
  backend/tests/integration/test_chat_v2_api.py \
  backend/tests/integration/test_chat_v3_api_execution_audit.py
```

Result: `87 passed`

## Gate sign-off decision

Phase 4 gate: PASS  
Phase 5 gate: PASS

No known blocker remains between Ask V1 baseline behavior and Ask V3 target behavior for the scoped Phase 4-5 boundary.
