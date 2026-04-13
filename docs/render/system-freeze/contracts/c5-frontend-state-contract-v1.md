# C5 Frontend State Contract v1

Status: Frozen frontend state and render correctness contract.

Owner: frontend conversation store + render layers.

## Scope

Defines normalized state shape, hot-path update rules, structural identity guarantees, and render invariants for progressive/virtualized views.

## Required Behaviors

1. State shape supports normalized access patterns.
2. Patch hot path must avoid global sort unless order changes.
3. Unchanged branches preserve object identity for memo effectiveness.
4. Render keys and ordering remain deterministic under batching/virtualization.
5. Presentation optimizations do not mutate canonical semantics.

## Performance-Safe Rules

- frame batching is apply/render batching only
- memoization must not suppress true content updates
- cache invalidation must key by data freshness fields (`itemId + updatedAt + mode`)

## Prohibited Behaviors

- frontend semantic coalescing that can diverge from backend canonical state
- forced reload without explicit mismatch/corruption classification
- unstable keying that breaks anchor/scroll integrity

## Reload Reason Taxonomy (Pre-Phase-8 Hardening)

Forced reload reason codes are standardized as:

1. `REPLAY_MISS`
2. `CONTRACT_ENVELOPE_INVALID`
3. `CONTRACT_THREAD_ID_MISMATCH`
4. `CONTRACT_EVENT_CURSOR_INVALID`
5. `APPLY_EVENT_FAILED`
6. `USER_INPUT_RESOLVE_TIMEOUT`
7. `USER_INPUT_RESOLVE_REQUEST_FAILED`
8. `STREAM_HEALTHCHECK_FAILED`
9. `MANUAL_RETRY`

Rules:

- forced reload must use one of the codes above
- forced reload with null/empty reason is invalid
- forced reload telemetry must preserve the last forced reason code

## Reload Policy Contract

Internal reload policy uses discriminated union:

- `kind: "forced"` requires `reason: ReloadReasonCode`
- `kind: "soft"` allows optional free-text `reason`

Rules:

- forced reload increments forced reload telemetry
- soft reload does not increment forced reload telemetry
- reload decisions must be produced by centralized policy mapping logic (no ad-hoc per-callsite classification)

## Pre-Split Store Guardrails

Before full Phase 08 store split, selector/domain boundaries must be explicit:

- `ThreadCoreState`
- `ThreadTransportState`
- `ThreadUiControlState`

Required selector entrypoints:

- `selectCore`
- `selectTransport`
- `selectUiControl`
