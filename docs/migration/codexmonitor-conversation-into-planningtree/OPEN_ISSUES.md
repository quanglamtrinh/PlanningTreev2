# Open Issues

## OI-001
- Severity: medium
- Issue: exact rollback or rewind support available from the target codex runtime has not been confirmed yet.
- Impact: affects final runtime strategy for `regenerate` and some `retry` flows.
- Follow-Up: confirm runtime capabilities during Phase 2 and record fallback policy in `DECISION_LOG.md`.

## OI-002
- Severity: medium
- Issue: dedicated storage format is now defined, but long-term migration from legacy simple messages into normalized rich records still needs a cutover strategy.
- Impact: replay and compatibility adapters must remain aligned during the dual-path period.
- Follow-Up: validate migration read rules during Phase 3 execution cutover.

## OI-003
- Severity: low
- Issue: planning composer remains disabled by default for the initial cutover, but future product behavior is intentionally undecided.
- Impact: avoid encoding this as a permanent product rule.
- Follow-Up: revisit only after planning embedding is stable.

## OI-004
- Severity: medium
- Issue: the current execution transport does not yet expose native live signals for `reasoning`, `tool_result`, `plan_step_update`, `diff_summary`, or `file_change_summary`.
- Impact:
  - Phase 5.1 backend live-path completeness is currently limited to `tool_call` and `plan_block`
  - the remaining passive semantics must stay replay-only on the backend live path until native transport support exists
- Follow-Up:
  - confirm native transport availability for the remaining passive semantics before expanding backend live-path claims
  - keep replay-only semantics available through durable snapshot replay or guarded terminal snapshot refresh without synthesizing fake live events

## OI-005
- Severity: medium
- Issue: approval live parity remains blocked because the current execution and planning runtime paths still use `approvalPolicy: never`.
- Impact:
  - `approval_request` can be made contract-ready and replay-safe in Phase 5.2
  - live approval emission and end-to-end approval lifecycle parity cannot be claimed until runtime policy changes
- Follow-Up:
  - keep approval explicitly documented as runtime-blocked in Phase 5.2 tracking
  - revisit only if runtime approval policy changes in a later phase

## OI-006
- Severity: low
- Issue: ask does not currently expose a clean normalized interactive request source on the v2 path in this repo.
- Impact:
  - current Phase 5.2 closeout covers execution and planning runtime-input lifecycle semantics
  - ask-specific interactive convergence should not be implied where no clean current-path source exists
- Follow-Up:
  - normalize additional interactive semantics on ask only when a durable v2 source exists and can be adopted without wrapper-owned shadow state
