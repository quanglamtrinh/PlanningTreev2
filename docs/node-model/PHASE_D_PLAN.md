# Phase D: Lifecycle and Confirmation for Nodes

Last updated: 2026-03-12

## Goal

Implement the node document lifecycle on top of the Phase C document model: confirmation endpoints, phase progression, automatic step-back when confirmed content changes, and explicit execution start.

## Delivered

### Lifecycle endpoints

- `POST /projects/{pid}/nodes/{nid}/confirm-task`
- `POST /projects/{pid}/nodes/{nid}/confirm-briefing`
- `POST /projects/{pid}/nodes/{nid}/confirm-spec`
- `POST /projects/{pid}/nodes/{nid}/start-execution`

### Phase progression

- `planning -> briefing_review` when task is confirmed
- `briefing_review -> spec_review` when briefing is confirmed
- `spec_review -> ready_for_execution` when spec is confirmed
- `ready_for_execution -> executing` when execution starts
- `ready_for_execution` or `executing` -> `closed` when the node completes

### Confirmation rules

- task confirmation requires non-empty `task.title` and `task.purpose`
- briefing confirmation requires `task_confirmed=true`
- spec confirmation requires `briefing_confirmed=true` and `spec_generated=true`
- confirmation endpoints are idempotent once the corresponding flag is already set

### Edit-triggered step-back

- content-changing task edits clear `task_confirmed`, `briefing_confirmed`, and `spec_confirmed`, then return the node to `planning` when task was already confirmed
- content-changing briefing edits clear `briefing_confirmed` and `spec_confirmed`, then return the node to `briefing_review` when briefing was already confirmed
- content-changing spec edits clear `spec_confirmed`, then return the node to `spec_review` when spec was already confirmed
- unchanged saves do not clear confirmations
- legacy `PATCH /projects/{pid}/nodes/{nid}` follows the same task-edit step-back behavior

### Additional guards

- all document edits reject while `phase=executing`
- superseded and `done` nodes remain read-only for edits and confirmation
- the first content-changing save to `spec.md` sets `state.yaml.spec_generated = true`
- completion only succeeds from `ready_for_execution` or `executing`

## Verification

- `python -m pytest backend/tests/unit/test_phase_transitions.py -q`
- `python -m pytest backend/tests/unit/test_auto_unconfirm.py -q`
- `python -m pytest backend/tests/unit/test_execution_guards.py -q`
- `python -m pytest backend/tests/integration/test_confirmation_endpoints.py -q`

## Follow-up

Phase E remains the next backend milestone for AI-assisted spec generation. Frontend document-panel work continues as a later phase on top of this lifecycle baseline.
