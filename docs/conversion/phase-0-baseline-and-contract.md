# Phase 0 - Baseline and Contract Freeze

Status: completed  
Estimate: 3-4 person-days (8%)

## 1. Goal

Freeze the behavior contract before implementation changes:

- Prevent behavior drift while replacing V2 core with V3 core.
- Define a clear acceptance gate for ask/execution/audit.
- Resolve cross-track documentation conflicts before coding.

## 2. In scope

- Freeze behavior matrix from current tests.
- Freeze API policy matrix for `/v1`, `/v2`, `/v3` during conversion.
- Freeze stream contract and error contract.
- Freeze naming contract: `thread_role` is canonical naming.
- Freeze V3 workflow control-plane API contract.
- Freeze compatibility bridge timing and read policy.
- Produce shared artifacts for later phases.

## 3. Out of scope

- Runtime/store implementation changes.
- Removing legacy routes/services.

## 4. Work breakdown

- [ ] Build baseline matrix from:
  - `backend/tests/integration/test_chat_v3_api_execution_audit.py`
  - `backend/tests/integration/test_phase6_execution_audit_cutover.py`
  - `backend/tests/unit/test_conversation_v3_projector.py`
  - `backend/tests/unit/test_ask_v3_rollout_phase6_7.py`
- [ ] Freeze route policy matrix:
  - `/v1` ask chat endpoints -> `invalid_request` (migration message)
  - `/v2` ask/execution/audit thread-role endpoints -> `invalid_request` (use `/v3` by-id)
  - `/v3` by-id reset -> ask only
- [ ] Freeze stream matrix:
  - first frame must be `thread.snapshot.v3`
  - incremental item event contract
  - reconnect guard `conversation_stream_mismatch`
- [ ] Freeze naming matrix:
  - lock canonical naming target as `thread_role` with JSON key `threadRole`
  - lock phased transition to avoid sequencing conflict:
    - Phase 1 canonicalizes domain/store and normalizes legacy `lane` on read
    - Phase 3 makes native `/v3` route output `threadRole`-primary
    - Phase 5 removes frontend active-path `lane` reads
    - Phase 7 removes `lane` emission and lane-based types/tests
  - baseline evidence may still include `lane` assertions while adapter-based `/v3` route path is active
  - canonical enum: `ask_planning | execution | audit`
- [ ] Freeze Workflow API V3 contract:
  - workflow state endpoint
  - workflow action endpoints
  - project-level workflow events endpoint
  - success/error envelope shape
  - active frontend workflow path must be `/v3` only
- [ ] Freeze user-input matrix:
  - resolve result -> `answer_submitted`
  - `activeUserInputRequests` signal updates must be correct
- [ ] Freeze compatibility bridge policy:
  - starts in Phase 2
  - read V3 first
  - fallback read-through from V2 then persist into V3
  - no V2 back-write on new path
  - explicit bridge mode: `enabled | allowlist | disabled`
  - disabled mode returns typed `conversation_v3_missing` for missing V3 snapshots
  - rollback path uses temporary allowlist mode only
- [ ] Record cross-track conflict note:
  - status mismatch in `docs/handoff/conversation-streaming-v2/progress.yaml`
  - ask-v3 phase 6-7 handoff already marked PASS

## 5. Deliverables

- `docs/conversion/artifacts/phase-0/behavior-matrix.md`
- `docs/conversion/artifacts/phase-0/policy-matrix.md`
- `docs/conversion/workflow-v3-control-plane-contract.md`
- `docs/conversion/artifacts/phase-0/open-questions.md` (if needed)
- `docs/conversion/artifacts/phase-0/decision-log.md`
- `docs/conversion/artifacts/phase-0/handoff-to-phase-1.md`

## 6. Exit criteria

- Behavior matrix is complete for ask/execution/audit.
- Team agrees on locked rules in `progress.yaml`.
- No ambiguity remains for:
  - stream open sequence
  - by-id role resolution
  - V3 workflow control-plane contract
  - `thread_role` naming contract
  - compatibility bridge timing/read policy
  - reset policy
  - user-input resolve semantics

## 7. Verification

- [ ] Run locked baseline suite:
  - `python -m pytest -q backend/tests/integration/test_chat_v3_api_execution_audit.py`
  - `python -m pytest -q backend/tests/integration/test_phase6_execution_audit_cutover.py`
  - `python -m pytest -q backend/tests/unit/test_conversation_v3_projector.py`
  - `python -m pytest -q backend/tests/unit/test_ask_v3_rollout_phase6_7.py`

## 8. Risks and mitigations

- Risk: matrix misses edge cases.
  - Mitigation: maintain a contract-gap list and escalate before Phase 1.
- Risk: conflict with older tracks.
  - Mitigation: publish conversion-track precedence note in phase artifacts.
