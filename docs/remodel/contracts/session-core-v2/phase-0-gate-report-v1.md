# Session Core V2 Phase 0 Gate Report v1

Date: 2026-04-20  
Status: PASS (Phase 0 complete)

## Scope

Phase 0 validates and freezes contracts for Session Core V2 before implementation:

1. Codex semantic parity map.
2. JSON-RPC lifecycle contract.
3. Core primitives and API surface contract.
4. Event/durability/idempotency/state-machine contracts.
5. Source-of-truth and domain-binding boundaries.

## Evidence Reviewed

PlanningTree contracts:

- `docs/remodel/contracts/session-core-v2/s0-codex-parity-method-map-v1.md`
- `docs/remodel/contracts/session-core-v2/s1-jsonrpc-lifecycle-contract-v1.md`
- `docs/remodel/contracts/session-core-v2/s2-core-primitives-v1.schema.json`
- `docs/remodel/contracts/session-core-v2/s3-session-http-api-v1.openapi.yaml`
- `docs/remodel/contracts/session-core-v2/s4-event-stream-contract-v1.md`
- `docs/remodel/contracts/session-core-v2/s4-event-envelope-v1.schema.json`
- `docs/remodel/contracts/session-core-v2/s4-server-request-envelope-v1.schema.json`
- `docs/remodel/contracts/session-core-v2/s5-durability-replay-contract-v1.md`
- `docs/remodel/contracts/session-core-v2/s6-idempotency-contract-v1.md`
- `docs/remodel/contracts/session-core-v2/s7-turn-state-machine-contract-v1.md`
- `docs/remodel/contracts/session-core-v2/s8-session-binding-contract-v1.md`

Codex references:

- `C:/Users/Thong/codex/codex-rs/app-server-protocol/src/protocol/v2.rs`
- `C:/Users/Thong/codex/codex-rs/app-server-protocol/schema/json/codex_app_server_protocol.v2.schemas.json`
- `C:/Users/Thong/codex/codex-rs/app-server-client/src/lib.rs`
- `C:/Users/Thong/codex/codex-rs/app-server-client/README.md`

## Gate Checklist

1. Runtime source-of-truth contract frozen: PASS  
   backend journal/snapshot authoritative, frontend projection-only.
2. Durability + replay contract frozen: PASS  
   monotonic `eventSeq`, cursor semantics, snapshot cadence, retention, cursor-expired behavior.
3. Idempotency contract frozen: PASS  
   `clientActionId` and `resolutionKey` required for mutating paths.
4. Turn state machine frozen: PASS  
   legal/illegal transitions and deterministic errors are explicit.
5. Codex method parity baseline: PASS  
   required thread/turn methods exist in Codex v2 protocol schema.
6. Handshake route boundary: PASS  
   `initialize` public, `initialized` internal by default.
7. Fixture and schema sanity checks: PASS  
   valid/invalid fixture intent preserved and parse checks passed.

## Tightening Applied During Review

1. `turn/steer.expectedTurnId` changed to required in OpenAPI.
2. `thread/metadata/update.gitInfo.originUrl` added to OpenAPI.
3. Thread active flags aligned to Codex (`waitingOnApproval`, `waitingOnUserInput`).
4. Event method enums extended with `thread/compacted`, `turn/diff/updated`, `turn/plan/updated`.
5. Lossless tier aligned closer to Codex app-server-client by promoting:
   - `item/reasoning/summaryTextDelta`
   - `item/reasoning/textDelta`

## Verification Result

Automated Phase 0 contract verification run (2026-04-20):

- `PHASE0_CONTRACT_CHECK=PASS`
- `checked_files=12`
- `codex_methods_verified=18`
- `fixtures_checked=4`

## Decision

Phase 0 is complete.  
Session Core V2 can proceed to Phase 1 (core skeleton implementation) without reopening contract scope.
