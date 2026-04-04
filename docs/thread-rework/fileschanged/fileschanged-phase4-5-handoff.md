# FilesChanged Rework - Phase 4-5 Handoff (Planning Skeleton)

Status: planning skeleton.

Date: 2026-04-03.

Owner scope: execution parity hardening and optional audit-lane onboarding.

## 1. Goal and boundary recap

Phase 4 target:

- lock execution parity with regression coverage and fixture-based verification

Phase 5 target:

- extend aligned file-change semantics to audit lane only after execution is stable

Out of scope for this handoff:

- broad production rollout
- removal of all legacy compatibility code

## 2. Implementation checklist

- [ ] build parity fixture set for execution file-change scenarios
- [ ] add integration tests for full execution run lifecycle -> file-change render output
- [ ] verify old turns still render via fallback and new turns always use migrated path
- [ ] decide audit-lane cutover scope and shared renderer boundaries
- [ ] wire audit adapter to canonical file-change model where applicable
- [ ] add audit-specific tests if Phase 5 is enabled

## 3. Expected write scope (planned)

- `backend/tests/integration/*execution*`
- `backend/tests/unit/*projector*`
- `frontend/tests/unit/*MessagesV3*`
- `frontend/tests/unit/*FileChangeToolRow*`
- `frontend/src/features/conversation/components/v3/*`
- `docs/thread-rework/fileschanged/*`

## 4. Acceptance evidence expected before closing Phase 4-5

- [ ] parity report for execution lane is green
- [ ] no regression in command/tool/reasoning rows caused by file-change changes
- [ ] fallback behavior is explicitly tested and documented
- [ ] audit-lane delta (if enabled) is tested and documented

## 5. Risks to watch

- parity drift between execution and audit representations
- flaky tests due to large diff payloads
- hidden dependency on legacy `outputFiles` paths in edge UIs

