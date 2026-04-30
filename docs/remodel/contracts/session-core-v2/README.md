# Session Core V2 Contracts (Codex-Parity)

Status: Frozen v1 (Phase 0 complete)  
Last updated: 2026-04-20  
Scope: Parallel rewrite lane for `Session Core V2`

This directory is the executable contract set for Session Core V2.
It is intentionally aligned to Codex app-server semantics and names.

## Contract Index

- `S0`: `s0-codex-parity-method-map-v1.md`
- `S1`: `s1-jsonrpc-lifecycle-contract-v1.md`
- `S2`: `s2-core-primitives-v1.schema.json`
- `S3`: `s3-session-http-api-v1.openapi.yaml`
- `S4`: `s4-event-stream-contract-v1.md`
- `S4-Schema-A`: `s4-event-envelope-v1.schema.json`
- `S4-Schema-B`: `s4-server-request-envelope-v1.schema.json`
- `S5`: `s5-durability-replay-contract-v1.md`
- `S6`: `s6-idempotency-contract-v1.md`
- `S7`: `s7-turn-state-machine-contract-v1.md`
- `S8`: `s8-session-binding-contract-v1.md`
- `Gate`: `phase-0-gate-report-v1.md`
- `Phase 1 Gate`: `phase-1-gate-report-v1.md`
- `Phase 2 Plan`: `phase-2-execution-plan-v1.md`
- `Phase 2 Gate`: `phase-2-gate-report-v1.md`
- `fixtures/`: canonical valid/invalid payload samples

## Source of truth rule

Backend Session Core V2 journal/snapshot is the sole runtime source of truth.
Frontend stores are projection/render caches only. Legacy conversation runtime,
chat-service, Codex-client, and V3 thread store/component paths have been
removed and must not be reintroduced as runtime owners.

## Change control

1. Do not change contracts ad hoc in feature PRs.
2. Any contract change must update:
   - relevant schema/OpenAPI/doc file
   - fixtures
   - parity harness expectations
3. Deterministic errors and state transitions are normative and cannot drift per caller.
