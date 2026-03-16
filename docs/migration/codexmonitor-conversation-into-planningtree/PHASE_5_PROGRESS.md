# Phase 5 Progress

## Overall Phase 5 Status
| Field | Value |
| --- | --- |
| Status | In progress |
| Current focus | Keep `5.1` and runtime-blocked `5.2` boundaries explicit, validate planning-v2 interactive convergence, and prepare `5.3` planning |
| Last updated | `2026-03-16` |
| Phase owner | `TBD` |

## Summary Board
| Subphase | Status | Owner | Validation Status | Latest Update | Open Issues |
| --- | --- | --- | --- | --- | --- |
| `5.1` | In progress | `TBD` | Partially validated | `2026-03-16` passive hardening and backend live-path boundary update | `P5-OI-001` |
| `5.2` | Complete | `TBD` | Partially validated | `2026-03-16` execution duplicate-suppression hardening and planning-v2 convergence | `P5-OI-002`, `P5-OI-003` |
| `5.3` | Not started | `TBD` | Not started | Planning only | `P5-OI-004`, `P5-OI-005`, `P5-OI-006`, `P5-OI-007` |

## Current Focus
- keep the dedicated Phase 5 package aligned with the actual repo state
- keep `5.1` replay-only backend semantics explicit until native transport support exists
- keep `5.2` approval live parity explicitly runtime-blocked while `approvalPolicy: never` remains
- use the package to prepare `5.3` lineage and fallback-policy decisions now that `5.2` runtime-input closeout has landed

## Completed
- `5.1` shared passive renderer and durable replay support are in place
- `5.1` passive-event targeting now rejects non-deterministic assistant attachment and logs observable diagnostics
- `5.1` backend live + replay completeness is implemented for `tool_call` and `plan_block`
- `5.2` execution-native runtime-input lifecycle is normalized, persisted, and rendered through the shared conversation contract
- `5.2` execution request resolution now suppresses duplicate terminal publish when local resolution and native callbacks overlap
- `5.2` active visible request selection now uses the latest unresolved request on the currently visible lineage
- `5.2` planning runtime-input lifecycle now converges on the same conversation-v2 contract through snapshot normalization, lifecycle event translation, and a planning v2 resolve route
- dedicated `PHASE_5_*` tracking files have been added to the migration docs

## In Progress
- `5.1` remaining passive semantics stay replay-only on the backend live path until native transport support exists
- `5.2` approval semantics are contract-ready and replay-safe, but live parity remains runtime-blocked
- ask interactive convergence remains limited to paths with a clean normalized source

## Not Started
- `5.3` lineage metadata
- `5.3` retry, continue, regenerate, and cancel semantics
- `5.3` runtime fallback policy for rewind-unavailable targets

## Blocked / At Risk
- `P5-OI-001`: missing native transport live signals for several passive semantics
- `P5-OI-002`: approval live parity remains blocked by `approvalPolicy: never`
- `P5-OI-003`: ask does not yet expose a clean normalized interactive source on the v2 path
- `P5-OI-004`: runtime rollback and rewind capability for `retry` and `regenerate` is not locked
- `P5-OI-005`: cancel/completion race semantics are not yet defined

## Phase 5.1 Status
### Status Table
| Field | Value |
| --- | --- |
| Status | In progress |
| Owner | `TBD` |
| Latest update | `2026-03-16` Phase 5.1 hardening landed |
| Validation status | Partially validated |
| Blockers | Native transport live signals are still missing for several passive semantics |
| Next recommended step | Keep replay-only semantics explicit and only widen backend live claims if native transport support appears |

### Completed Implementation Items
- deterministic assistant-only passive-event targeting on the shared reducer path
- passive renderer and durable replay support for known passive semantics
- backend live emission, persistence, and terminal reconciliation for `tool_call`
- backend live emission, persistence, and replace-in-place reconciliation for `plan_block`

### Remaining Implementation Items
- widen backend live support only if native transport signals exist for the remaining passive semantics
- keep ask and planning convergence limited to clean normalized sources
- maintain doc and validation coverage for replay-only semantics

### Validation Status
- reducer tests cover deterministic passive targeting and duplicate-delivery idempotency
- backend tests cover `tool_call` and `plan_block` live emission, persistence, and reconciliation
- replay fidelity remains unproven for native live delivery of the replay-only passive semantics because the transport does not expose them

### Blockers
- `P5-OI-001`

### Next Recommended Steps
- do not widen backend live-path claims beyond the current support matrix
- preserve replay-only semantics through durable snapshot replay or guarded terminal snapshot refresh
- keep 5.1 documentation aligned with the actual transport boundary

## Phase 5.2 Status
### Status Table
| Field | Value |
| --- | --- |
| Status | Complete |
| Owner | `TBD` |
| Latest update | `2026-03-16` execution duplicate-suppression hardening and planning-v2 convergence landed |
| Validation status | Partially validated |
| Blockers | Approval live parity remains runtime-blocked; ask still lacks a clean normalized interactive source on the v2 path |
| Next recommended step | Hold the `5.2` boundary steady, keep approval runtime-blocked in docs, and move active implementation focus to `5.3` |

### Completed Implementation Items
- normalized `request_resolved` event added to the shared conversation-v2 contract
- shared render-model support for `approval_request`, `user_input_request`, and `user_input_response`
- execution-native request creation, request resolution, and user-response persistence
- execution duplicate terminal-publish suppression for local resolve plus native callback overlap
- shared request-actions hook for host-owned submit surfaces
- latest-unresolved active request selection on the currently visible lineage
- planning snapshot normalization, event translation, and resolve routing now converge planning runtime-input semantics on the same v2 request contract

### Remaining Implementation Items
- keep approval live parity explicitly runtime-blocked until runtime policy changes
- normalize ask interactive semantics only when a clean durable v2 source exists
- keep replay/reconnect and host submit behavior aligned with the documented contract

### Validation Status
- reducer and renderer tests cover `request_user_input`, `request_resolved`, and `user_input_resolved`
- host tests cover latest-unresolved active request selection plus execution and planning host submission through the v2 resolve routes
- backend tests cover request creation, duplicate-suppression hardening, planning normalization, persistence, and publish ordering on the execution and planning paths
- approval live-path parity is intentionally unvalidated because it is runtime-blocked

### Blockers
- `P5-OI-002`
- `P5-OI-003`

### Next Recommended Steps
- keep approval documented as runtime-blocked rather than partially implied
- keep submit controls host-owned unless the shared surface intentionally becomes the primary submit surface later
- do not claim ask interactive convergence where no clean normalized source exists

## Phase 5.3 Status
### Status Table
| Field | Value |
| --- | --- |
| Status | Not started |
| Owner | `TBD` |
| Latest update | Planning baseline only |
| Validation status | Not started |
| Blockers | Runtime fallback and cancel semantics are not locked |
| Next recommended step | Lock lineage metadata, fallback policy, and cancel semantics before action wiring begins |

### Completed Implementation Items
- none

### Remaining Implementation Items
- define durable lineage metadata and supersession markers
- lock fallback policy for rewind-unavailable runtimes
- implement `cancel` as terminalization on the current lineage
- implement `retry`, `continue`, and `regenerate`
- add replay/reconnect coverage for lineage-changing actions

### Validation Status
- no 5.3 validation has started

### Blockers
- `P5-OI-004`
- `P5-OI-005`
- `P5-OI-006`
- `P5-OI-007`

### Next Recommended Steps
- lock the runtime capability and fallback policy before UI or route work starts
- keep superseded-history replay explicit from the beginning
- separate cancel semantics from branch-creation semantics
