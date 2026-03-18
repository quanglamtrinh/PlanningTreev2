# Phase 5 Progress

## Overall Phase 5 Status
| Field | Value |
| --- | --- |
| Status | In progress |
| Current focus | Keep `5.1` and runtime-blocked `5.2` boundaries explicit, validate execution-first `5.3` replay/reconnect behavior, and keep the dedicated Phase 5 package aligned with the actual repo state |
| Last updated | `2026-03-16` |
| Phase owner | `TBD` |

## Summary Board
| Subphase | Status | Owner | Validation Status | Latest Update | Open Issues |
| --- | --- | --- | --- | --- | --- |
| `5.1` | In progress | `TBD` | Partially validated | `2026-03-16` passive hardening and backend live-path boundary update | `P5-OI-001` |
| `5.2` | Complete | `TBD` | Partially validated | `2026-03-16` execution duplicate-suppression hardening and planning-v2 convergence | `P5-OI-002`, `P5-OI-003` |
| `5.3` | In progress | `TBD` | Partially validated | `2026-03-16` execution-first lineage-aware actions and replay model landed | none blocking |

## Current Focus
- keep the dedicated Phase 5 package aligned with the actual repo state
- keep `5.1` replay-only backend semantics explicit until native transport support exists
- keep `5.2` approval live parity explicitly runtime-blocked while `approvalPolicy: never` remains
- finish `5.3` replay/reconnect validation and manual QA without overstating the execution-first scope

## Completed
- `5.1` shared passive renderer and durable replay support are in place
- `5.1` passive-event targeting now rejects non-deterministic assistant attachment and logs observable diagnostics
- `5.1` backend live + replay completeness is implemented for `tool_call` and `plan_block`
- `5.2` execution-native runtime-input lifecycle is normalized, persisted, and rendered through the shared conversation contract
- `5.2` execution request resolution now suppresses duplicate terminal publish when local resolution and native callbacks overlap
- `5.2` active visible request selection now uses the latest unresolved request on the currently visible lineage
- `5.2` planning runtime-input lifecycle now converges on the same conversation-v2 contract through snapshot normalization, lifecycle event translation, and a planning v2 resolve route
- `5.3` execution conversation sends now seed durable lineage and lazily backfill legacy execution transcripts before snapshot return or action validation
- `5.3` execution-only action routes now exist for `continue`, `retry`, `regenerate`, and `cancel`
- `5.3` shared execution rendering now supports `status_block` plus collapsed inline replay groups for superseded or off-lineage execution history
- dedicated `PHASE_5_*` tracking files have been added to the migration docs

## In Progress
- `5.1` remaining passive semantics stay replay-only on the backend live path until native transport support exists
- `5.2` approval semantics are contract-ready and replay-safe, but live parity remains runtime-blocked
- ask interactive convergence remains limited to paths with a clean normalized source
- `5.3` replay/reconnect closeout coverage and manual QA are still being finished

## Not Started
- no additional Phase 5.3 host scopes are planned beyond the execution-first boundary in this phase

## Blocked / At Risk
- `P5-OI-001`: missing native transport live signals for several passive semantics
- `P5-OI-002`: approval live parity remains blocked by `approvalPolicy: never`
- `P5-OI-003`: ask does not yet expose a clean normalized interactive source on the v2 path

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
| Status | In progress |
| Owner | `TBD` |
| Latest update | `2026-03-16` execution-first lineage-aware actions and replay model landed |
| Validation status | Partially validated |
| Blockers | No open policy blockers; remaining closeout work is replay/reconnect coverage and manual QA |
| Next recommended step | Finish replay/reconnect validation and keep the execution-first scope explicit in docs and host behavior |

### Completed Implementation Items
- ordinary execution sends now seed durable lineage for send-created user and assistant messages
- legacy execution transcripts with empty lineage are repaired lazily and idempotently before snapshot return or action validation
- visible execution lineage is selected from the latest eligible unsuperseded assistant head by durable transcript order
- execution-only v2 routes now exist for `continue`, `retry`, `regenerate`, and `cancel`
- `continue` uses assistant-to-assistant parenting and returns `action_status = unavailable` when the runtime cannot prepare a resumable thread
- `retry` and `regenerate` create explicit new branches, while `regenerate` durably marks the replaced completed assistant result with `superseded_by_message_id`
- `cancel` terminalizes the active execution stream without creating a branch
- the shared execution surface now renders `status_block` and collapsed inline replay groups for superseded or off-lineage history

### Remaining Implementation Items
- expand replay/reconnect coverage for `retry`, `regenerate`, and `cancel`
- add closeout validation for unavailable action outcomes when the runtime cannot prepare continue or fork behavior
- complete manual QA for collapsed replay presentation, visible action availability, and cancel/reload behavior

### Validation Status
- backend unit tests cover execution lineage seeding and backfill plus lineage population for `continue`, `retry`, `regenerate`, and `cancel`
- backend integration tests cover accepted `continue` and `cancel` route behavior on the execution v2 path
- frontend unit tests cover `status_block` rendering, collapsed replay grouping, and local supersession patching for regenerate
- replay/reconnect validation remains incomplete for all lineage-changing actions

### Blockers
- none

### Next Recommended Steps
- add replay/reconnect coverage for `retry`, `regenerate`, and `cancel`
- keep planning and ask action scopes explicitly out of Phase 5.3
- keep the docs aligned with the execution-first implementation boundary
