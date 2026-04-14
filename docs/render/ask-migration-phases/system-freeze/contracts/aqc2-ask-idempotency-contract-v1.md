# AQC2 - Ask Idempotency Contract v1

Status: Frozen contract.

Last updated: 2026-04-14.

- Ask lane turn start must support idempotency key replay without duplicate turn creation.
- Repeated request with same key and lane context must return the same accepted turn identity.
- Idempotency storage must be bounded and lane-scoped.
