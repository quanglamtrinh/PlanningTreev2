# Contracts (C1-C6)

This directory stores canonical phase contracts frozen for the v1 optimization wave.

## Contract Files

- `c1-event-stream-contract-v1.md`
- `c1-event-stream-envelope-v1.schema.json`
- `c1-event-stream-control-envelope-v1.schema.json`
- `c1-event-stream-bridge-policy-v1.md`
- `c2-replay-resync-contract-v1.md`
- `c3-lifecycle-gating-contract-v1.md`
- `c4-durability-contract-v1.md`
- `c4-mini-journal-spec-v1.md`
- `c5-frontend-state-contract-v1.md`
- `c6-queue-contract-v1.md`
- `fixtures/`:
  - `c1-business-valid-v1.json`
  - `c1-business-invalid-missing-event-id-v1.json`
  - `c1-control-valid-v1.json`
  - `c1-control-invalid-missing-thread-id-v1.json`

## Usage

- Backend and frontend implementation must map directly to these contracts.
- Phase docs must cite contract IDs exactly (`C1`..`C6`).
- Any contract change requires Decision Pack change-control approval.
