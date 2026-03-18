# Phase 5 Open Issues

## Summary Table
| Issue ID | Title | Affected Subphase | Classification | Status |
| --- | --- | --- | --- | --- |
| `P5-OI-001` | Native transport coverage for remaining passive live semantics | `5.1` | Non-blocking for current replay-only boundary; blocking for wider backend live-parity claims | Open |
| `P5-OI-002` | Approval live parity blocked by `approvalPolicy: never` | `5.2` | Runtime-blocked | Open |
| `P5-OI-003` | Ask lacks a clean normalized interactive source on the v2 path | `5.2` | Non-blocking for current 5.2 closeout | Open |
| `P5-OI-004` | Runtime rollback and rewind capability for `retry` and `regenerate` | `5.3` | Resolved by explicit branch fallback | Closed |
| `P5-OI-005` | Cancel/completion race terminalization policy | `5.3` | Resolved by gateway-owned terminalization policy | Closed |
| `P5-OI-006` | Superseded-branch replay presentation defaults | `5.3` | Resolved by collapsed inline replay default | Closed |
| `P5-OI-007` | Durable lineage metadata and action ownership model | `5.3` | Resolved by execution-first lineage model and route ownership rules | Closed |

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

#### `P5-OI-003` - Ask lacks a clean normalized interactive source on the v2 path
- Affected subphase: `5.2`
- Description:
  - planning now converges on the shared request contract in this repo, but ask does not currently expose a clean durable interactive request source on the v2 path
- Why it matters:
  - ask interactive convergence should not be implied where no clean source exists
- Current default assumption:
  - current `5.2` closeout in this repo covers execution and planning runtime-input lifecycle semantics; ask remains excluded until it has a clean normalized source
- What decision or experiment is needed:
  - adopt ask interactive semantics only when a clean normalized v2 source exists and can be used without wrapper-owned shadow state
- Classification:
  - Non-blocking for the current `5.2` closeout

### Phase 5.3
- No open Phase 5.3 policy issues remain.
- Remaining Phase 5.3 work is validation and manual QA, not unresolved lineage or fallback-policy decisions.

#### Closed `P5-OI-004` - Runtime rollback and rewind capability for `retry` and `regenerate`
- Resolution:
  - `retry` and `regenerate` now use explicit new execution branches instead of claiming in-place rewind
  - prior branch history remains durable and replayable

#### Closed `P5-OI-005` - Cancel/completion race terminalization policy
- Resolution:
  - gateway-owned cancel clears active stream ownership before late callbacks can restamp terminal state
  - accepted cancel terminalizes the current execution stream without fabricating a branch
  - if completion wins first, cancel returns an idempotent no-op outcome

#### Closed `P5-OI-006` - Superseded-branch replay presentation defaults
- Resolution:
  - the shared execution surface now uses collapsed inline replay as the default presentation for superseded or off-lineage history
  - collapsed replay remains expandable and preserves branch-local passive semantics, request history, and terminal metadata

#### Closed `P5-OI-007` - Durable lineage metadata and action ownership model
- Resolution:
  - execution sends now seed durable lineage and lazily backfill legacy execution transcripts with empty lineage
  - execution action ownership is route-driven and lineage-aware for `continue`, `retry`, `regenerate`, and `cancel`

## Runtime Uncertainty
- `P5-OI-001` - native transport coverage for replay-only passive semantics
- `P5-OI-002` - approval live parity blocked by current runtime policy

## Replay Fidelity Risks
- `P5-OI-001` - replay-only passive semantics being mistaken for live-complete semantics
- `P5-OI-003` - ask interactive semantics being implied without a durable v2 source

## Fallback Policy Gaps
- `P5-OI-001` - passive semantics without native live transport support

## Decisions That Must Be Made Before Completion
### Blocking Decisions
- no additional blocking policy decisions remain for the current execution-first 5.3 scope

### Boundary Decisions That Must Stay Explicit
- Keep `P5-OI-001` explicit while replay-only passive semantics remain transport-gated.
- Keep `P5-OI-002` explicit while `approvalPolicy: never` remains.
- Keep `P5-OI-003` explicit until ask exposes a clean normalized interactive source.
