# Phase 5 Validation

## Validation Rules
- Treat this file as the operational checklist for Phase 5 validation.
- Mark items complete only when code, tests, and replay behavior agree.
- Validate semantic convergence, not only surface appearance.
- Do not mark a subphase complete while runtime-blocked or replay-only boundaries remain undocumented.

## Cross-Subphase Validation
### Current Status
- In progress

### Unit Test Expectations
- [x] normalized conversation types represent known passive and interactive semantics
- [x] reducers preserve deterministic attachment and idempotent upsert behavior
- [x] malformed known semantics degrade safely instead of crashing the shared surface
- [ ] lineage-aware action reducers are covered

### Integration Test Expectations
- [x] implemented execution live paths converge with durable replay for current `5.1` and `5.2` semantics
- [x] host wrappers do not own a second authoritative request lifecycle on the execution v2 path
- [ ] ask and planning interactive convergence is covered where a clean normalized source exists

### Replay / Reconnect Expectations
- [x] reload reconstructs passive and interactive semantics from normalized durable messages on the implemented paths
- [x] reconnect does not duplicate passive render items or reopen resolved requests as active UI on the execution path
- [ ] reconnect after lineage-changing actions is covered

### Manual QA Scenarios
- [ ] reload during a passive-rich execution turn
- [ ] reload during an active runtime-input request
- [ ] confirm host-specific framing still behaves correctly in ask, planning, and execution

### Regression Guardrails
- [x] Phase 3/4 text-first behavior remains intact
- [x] host wrappers still own shell framing and outer submit affordances
- [x] no Phase 5 subphase requires shell migration
- [ ] no Phase 6 work has been pulled into Phase 5 closeout

## Phase 5.1 Validation
### Current Status
- Partially validated

### Unit Test Expectations
- [x] reducer tests cover deterministic passive targeting
- [x] reducer tests cover duplicate-delivery idempotency for passive parts
- [x] render-model tests cover passive parts and malformed fallback behavior
- [ ] native live event tests exist for all passive semantics

### Integration Test Expectations
- [x] backend tests cover `tool_call` live emission, persistence, and terminal reconciliation
- [x] backend tests cover `plan_block` live emission, persistence, and replace-in-place reconciliation
- [ ] backend tests cover native live emission for `reasoning`, `tool_result`, `plan_step_update`, `diff_summary`, and `file_change_summary`

### Replay / Reconnect Expectations
- [x] replay-only passive semantics remain renderable from durable state
- [x] reconnect does not duplicate `tool_call` or `plan_block` render items on the implemented path
- [ ] reconnect coverage exists for any future native live path of the remaining passive semantics

### Manual QA Scenarios
- [ ] inspect mixed text + passive transcript rendering in execution
- [ ] inspect planning passive replay where normalized `tool_call` content appears
- [ ] inspect safe fallback behavior for malformed passive payloads

### Regression Guardrails
- [x] backend live-path claims remain limited to `tool_call` and `plan_block`
- [x] replay-only semantics remain explicitly documented as replay-only
- [x] passive semantics attach only to deterministic assistant targets

## Phase 5.2 Validation
### Current Status
- Partially validated

### Unit Test Expectations
- [x] reducer applies `approval_request`, `request_user_input`, `request_resolved`, and `user_input_resolved`
- [x] latest-unresolved active request selection is covered
- [x] historical resolved requests remain replayable but inactive
- [x] malformed interactive payloads degrade safely

### Integration Test Expectations
- [x] execution streaming emits and persists normalized `request_user_input`
- [x] `serverRequest/resolved` maps to `request_resolved`
- [x] successful runtime-input resolution persists a `user_input_response`
- [ ] planning adapter snapshot and events normalize planner request state into the same v2 shapes
- [ ] approval live-path parity is validated end-to-end

### Replay / Reconnect Expectations
- [x] reload during an active request restores exactly one active visible unresolved request on the execution path
- [x] that active request is the latest unresolved request on the currently visible lineage
- [x] reload after request resolution preserves historical request/response state without reopening controls
- [ ] ask/planning reconnect behavior is covered where interactive semantics exist

### Manual QA Scenarios
- [ ] reload while an execution runtime-input request is active
- [ ] verify host-owned submit controls and transcript state stay aligned after submit
- [ ] inspect approval rendering from replay-safe snapshots

### Regression Guardrails
- [x] host submit surfaces derive from v2 request state on the execution path
- [x] approval remains documented as runtime-blocked while `approvalPolicy: never` remains
- [x] historical resolved requests do not reopen as active UI
- [ ] no ask/planning interactive convergence is implied without a clean normalized source

## Phase 5.3 Validation
### Current Status
- Not started

### Unit Test Expectations
- [ ] lineage metadata creation and supersession are covered
- [ ] cancel terminalizes the current lineage without creating a new branch
- [ ] retry, continue, and regenerate obey explicit fallback policy

### Integration Test Expectations
- [ ] action routes enforce ownership and terminal-state rules
- [ ] superseded branches remain replayable after action execution
- [ ] fallback behavior is covered when the runtime cannot rewind

### Replay / Reconnect Expectations
- [ ] replay after retry preserves prior and superseding branches where required
- [ ] reconnect after cancel preserves terminalization on the current lineage
- [ ] reconnect after lineage mutation does not attach to the wrong branch

### Manual QA Scenarios
- [ ] cancel an active operation and reload
- [ ] retry and regenerate a completed branch and inspect replay
- [ ] continue from the correct lineage state and reload

### Regression Guardrails
- [ ] cancel is not implemented as pseudo-regenerate
- [ ] superseded history does not disappear from durable replay
- [ ] action rollout does not require shell migration or Phase 6 cleanup work
