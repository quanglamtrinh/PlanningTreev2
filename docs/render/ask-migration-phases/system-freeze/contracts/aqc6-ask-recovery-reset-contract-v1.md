# AQC6 - Ask Recovery and Reset Contract v1

Status: Frozen contract.

Last updated: 2026-04-14.

- Queue persistence/hydration must avoid message loss and duplicate send after reload/reconnect.
- Ask reset behavior for queued entries must be explicit and deterministic.
- Recovery path must preserve lane safety and idempotency semantics.
