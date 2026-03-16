# Phase 5 Open Issues

## Summary Table
| Issue ID | Title | Affected Subphase | Classification | Status |
| --- | --- | --- | --- | --- |
| `P5-OI-001` | Native transport coverage for remaining passive live semantics | `5.1` | Non-blocking for current replay-only boundary; blocking for wider backend live-parity claims | Open |
| `P5-OI-002` | Approval live parity blocked by `approvalPolicy: never` | `5.2` | Runtime-blocked | Open |
| `P5-OI-003` | Ask and planning lack a clean normalized interactive source on the v2 path | `5.2` | Non-blocking for execution-native closeout | Open |
| `P5-OI-004` | Runtime rollback and rewind capability for `retry` and `regenerate` | `5.3` | Blocking | Open |
| `P5-OI-005` | Cancel/completion race terminalization policy | `5.3` | Blocking | Open |
| `P5-OI-006` | Superseded-branch replay presentation defaults | `5.3` | Non-blocking | Open |
| `P5-OI-007` | Durable lineage metadata and action ownership model | `5.3` | Blocking | Open |

## Open Issues By Subphase

### Phase 5.1

#### `P5-OI-001` - Native transport coverage for remaining passive live semantics
- Affected subphase: `5.1`
- Description:
  - the current execution transport does not expose native live signals for `reasoning`, `tool_result`, `plan_step_update`, `diff_summary`, or `file_change_summary`
- Why it matters:
  - backend live-path completeness cannot be claimed for semantics the transport cannot emit natively and deterministically
- Current default assumption:
  - those semantics remain replay-only on the backend live path and appear through durable snapshot replay or guarded terminal snapshot refresh
- What decision or experiment is needed:
  - confirm native transport availability before widening backend live claims
- Classification:
  - Non-blocking for the current `5.1` replay-only boundary
  - Blocking for any future claim of full backend live parity across the passive set

### Phase 5.2

#### `P5-OI-002` - Approval live parity blocked by `approvalPolicy: never`
- Affected subphase: `5.2`
- Description:
  - execution and planning runtime paths still use `approvalPolicy: never`
- Why it matters:
  - `approval_request` can be contract-ready and replay-safe, but live approval emission and end-to-end approval lifecycle parity cannot be claimed
- Current default assumption:
  - approval remains documented as runtime-blocked while the policy remains unchanged
- What decision or experiment is needed:
  - revisit only if runtime approval policy changes in a later phase
- Classification:
  - Runtime-blocked

#### `P5-OI-003` - Ask and planning lack a clean normalized interactive source on the v2 path
- Affected subphase: `5.2`
- Description:
  - ask and planning do not currently expose a clean durable interactive request source on the v2 path in this repo
- Why it matters:
  - ask/planning interactive convergence should not be implied where no clean source exists
- Current default assumption:
  - current `5.2` closeout in this repo is execution-native for runtime-input lifecycle semantics
- What decision or experiment is needed:
  - adopt ask/planning interactive semantics only when a clean normalized v2 source exists and can be used without wrapper-owned shadow state
- Classification:
  - Non-blocking for the current execution-native closeout

### Phase 5.3

#### `P5-OI-004` - Runtime rollback and rewind capability for `retry` and `regenerate`
- Affected subphase: `5.3`
- Description:
  - exact rollback or rewind support from the target runtime has not been confirmed
- Why it matters:
  - `retry` and `regenerate` fallback policy depends on whether true rewind exists
- Current default assumption:
  - if true rewind is unavailable, `retry` and `regenerate` fall back to explicit superseding lineage rather than pretending the old branch disappeared
- What decision or experiment is needed:
  - confirm runtime capability and lock fallback policy before `5.3` closeout
- Classification:
  - Blocking

#### `P5-OI-005` - Cancel/completion race terminalization policy
- Affected subphase: `5.3`
- Description:
  - `cancel` belongs to active-operation control semantics, but the policy for races between cancel and natural completion is not locked yet
- Why it matters:
  - race ambiguity can create duplicate terminal states or synthetic branch behavior
- Current default assumption:
  - if completion is durably committed first, cancel becomes a no-op for visible lineage mutation and must not fabricate a second terminal branch
- What decision or experiment is needed:
  - define gateway/runtime precedence behavior and prove it with integration tests
- Classification:
  - Blocking

#### `P5-OI-006` - Superseded-branch replay presentation defaults
- Affected subphase: `5.3`
- Description:
  - superseded branches must remain replayable, but the minimum shared replay presentation is not yet pinned down
- Why it matters:
  - lineage may exist durably but still be difficult to inspect if the shared replay affordance is under-specified
- Current default assumption:
  - superseded branches remain replayable in the shared contract and host wrappers may differ in outer framing
- What decision or experiment is needed:
  - confirm the minimum shared replay affordance needed to inspect superseded lineage without forcing shell parity
- Classification:
  - Non-blocking

#### `P5-OI-007` - Durable lineage metadata and action ownership model
- Affected subphase: `5.3`
- Description:
  - the durable lineage metadata model and action ownership rules are not yet locked for retry, continue, regenerate, and cancel
- Why it matters:
  - action semantics cannot be implemented safely without an explicit model for branch identity, supersession, and ownership
- Current default assumption:
  - action availability will remain lineage-aware, durable, and terminal-state-aware rather than wrapper-local
- What decision or experiment is needed:
  - lock the lineage metadata model and action ownership rules before action routes or controls are introduced
- Classification:
  - Blocking

## Runtime Uncertainty
- `P5-OI-001` - native transport coverage for replay-only passive semantics
- `P5-OI-002` - approval live parity blocked by current runtime policy
- `P5-OI-004` - rollback and rewind capability for lineage-aware actions
- `P5-OI-005` - cancel/completion race behavior under runtime and gateway timing

## Replay Fidelity Risks
- `P5-OI-001` - replay-only passive semantics being mistaken for live-complete semantics
- `P5-OI-003` - ask/planning interactive semantics being implied without a durable v2 source
- `P5-OI-006` - superseded-branch replay presentation remaining under-specified
- `P5-OI-007` - lineage metadata and ownership rules not being explicit enough for deterministic replay

## Fallback Policy Gaps
- `P5-OI-001` - passive semantics without native live transport support
- `P5-OI-004` - explicit fallback for `retry` and `regenerate` when rewind is unavailable
- `P5-OI-005` - visible cancel behavior when completion wins the race

## Decisions That Must Be Made Before Completion
### Blocking Decisions
- Resolve `P5-OI-004` before `5.3` action rollout.
- Resolve `P5-OI-005` before `cancel` can close out.
- Resolve `P5-OI-007` before lineage-aware actions are introduced.

### Boundary Decisions That Must Stay Explicit
- Keep `P5-OI-001` explicit while replay-only passive semantics remain transport-gated.
- Keep `P5-OI-002` explicit while `approvalPolicy: never` remains.
- Keep `P5-OI-003` explicit until ask or planning exposes a clean normalized interactive source.
