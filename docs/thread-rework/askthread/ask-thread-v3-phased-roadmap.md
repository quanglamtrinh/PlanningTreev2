# Ask Thread V3 Phased Roadmap

Status: planning skeleton for implementation.

Last updated: 2026-04-03.

## 1. Scope and locked decisions

This roadmap assumes the following decisions are frozen:

- Ask has its own V3 lane (`ask`) and does not reuse execution/audit lane semantics.
- Ask uses shared V3 by-id route namespace and Thread Registry as the source of truth for thread binding.
- Ask transcript is for Q&A/info and clarification context only.
- Ask metadata shell is the canonical ask UX surface and is not attached to thread body rendering.
- Existing CTA/action controls stay in node-detail right panel (not inside ask thread).
- Ask remains usable after Finish Task, but only in strict read-only mode.
- Frame/Clarify/Spec operations can still run, but code/file writes are backend-owned and artifact-scoped only.
- Rollout follows gated stages and auto-enables new gate at the planned phase boundary.

## 2. Non-goals

- No behavior regression for execution/audit V3 lanes.
- No broad "agent writes to workspace" for ask lane.
- No reintroduction of legacy V1 as the default path after hard cutover.

## 3. Phase split and effort estimate

Total effort baseline: 100%.

| Phase | Name | Effort % | Primary owners |
|---|---|---:|---|
| 0 | Contract freeze + guard design | 8% | BE + FE lead |
| 1 | Backend ask-lane foundation (V3 + registry) | 14% | BE |
| 2 | Ask runtime guard and write-scope enforcement | 12% | BE |
| 3 | Frontend ask lane + metadata shell integration | 20% | FE |
| 4 | Frame/Clarify/Spec action wiring on V3 ask | 16% | BE + FE |
| 5 | Parity and regression hardening | 16% | QA + BE + FE |
| 6 | Gate rollout and stabilization | 9% | BE + FE + QA |
| 7 | Hard cutover cleanup and closure | 5% | BE + FE |

## 4. Detailed phase skeleton

## Phase 0 (8%) - Contract freeze + guard design

Goals:

- Freeze ask-lane V3 contract and avoid scope drift.
- Freeze guard policy: ask read-only by default, workflow artifact writes only via dedicated services.

Implementation checklist:

- Define `ask` lane contract in frontend/backend types.
- Freeze API shape for shared by-id route usage for ask lane.
- Freeze metadata shell ownership boundary vs transcript boundary.
- Freeze write policy matrix:
  - ask chat turns: read-only sandbox.
  - frame/clarify/spec generation: structured output -> backend writes artifacts.

Outputs:

- Contract appendix merged into docs.
- Guard matrix approved.

Exit criteria:

- No open architecture question remains for ask migration start.

## Phase 1 (14%) - Backend ask-lane foundation (V3 + registry)

Goals:

- Make ask lane first-class in V3 backend path.
- Ensure thread binding is registry-first.

Implementation checklist:

- Extend lane/domain typing and lane validation for ask.
- Ensure ask lane is supported by V3 snapshot/read/stream path.
- Use Thread Registry for ask binding and resume/rebuild flow.
- Keep execution/audit behavior unchanged.

Outputs:

- Backend V3 ask lane bootstrap working on staging.
- Thread registry entries created/read for ask lane.

Exit criteria:

- Ask lane can open/read/stream via V3 endpoints with stable thread identity.

## Phase 2 (12%) - Ask runtime guard and write-scope enforcement

Goals:

- Guarantee ask lane never mutates workspace code directly.
- Guarantee only artifact-scoped writes happen in workflow operations.

Implementation checklist:

- Force ask lane turns to `read_only` sandbox profile.
- Add server-side enforcement so ask chat turns reject write attempts (defense in depth).
- Keep frame/clarify/spec generators in structured-output mode.
- Route actual file writes through backend services only:
  - `frame.md`
  - `clarify.json`
  - `spec.md`
  - required workflow metadata sidecars (`*.meta.json`, `*_gen.json`) only.

Outputs:

- Guard tests for ask read-only runtime.
- Write-scope tests for workflow artifact-only mutation.

Exit criteria:

- No non-artifact write path remains reachable from ask interactions.

## Phase 3 (20%) - Frontend ask lane + metadata shell integration

Goals:

- Move ask surface to V3 route/store while preserving ask UX intent.
- Keep metadata shell independent from transcript body.

Implementation checklist:

- Route ask lane through shared V3 by-id path.
- Wire ask lane into V3 store consumption.
- Implement/render ask metadata shell from metadata source, not from transcript coupling.
- Ensure reset ask thread does not destroy metadata shell state.
- Keep node-detail right-panel CTA behavior unchanged.

Outputs:

- Ask lane on V3 UI path with metadata shell parity.
- UX regression checklist for shell persistence.

Exit criteria:

- Ask UX behaves as designed without depending on thread-body hacks.

## Phase 4 (16%) - Frame/Clarify/Spec action wiring on V3 ask

Goals:

- Keep frame/clarify/spec fully usable after ask migration.
- Maintain separation: ask thread = Q&A, workflow writes = service-owned actions.

Implementation checklist:

- Wire frame/clarify/spec actions to dedicated backend services.
- Reflect action status/result in metadata shell.
- Ensure actions do not require direct agent workspace writes.
- Preserve current CTA placement in node-detail panel.

Outputs:

- End-to-end action flow (generate -> review -> confirm) on V3 ask lane.

Exit criteria:

- User can complete shaping workflow without legacy ask path.

## Phase 5 (16%) - Parity and regression hardening

Goals:

- Prove no functional regression from V1 ask behavior baseline.
- Lock guard and shell behavior with automated tests.

Implementation checklist:

- Backend tests:
  - ask read-only enforcement
  - registry binding correctness
  - artifact write-scope enforcement
- Frontend tests:
  - ask route/store behavior
  - metadata shell rendering and persistence across reset
  - CTA parity (still in node-detail panel)
- Integration tests:
  - ask after Finish Task remains available in read-only mode
  - frame/clarify/spec actions still work

Outputs:

- Ask parity report and pass/fail matrix.

Exit criteria:

- Parity gate green in CI.

## Phase 6 (9%) - Gate rollout and stabilization

Goals:

- Roll out ask V3 by gate with safe fallback.
- Auto-enable the new gate at planned rollout step.

Implementation checklist:

- Introduce/enable ask-specific rollout gate.
- Stage rollout:
  - internal
  - canary
  - broader rollout
- Add monitoring counters:
  - V3 ask stream failures/reconnect
  - ask guard violations
  - action failure rates (frame/clarify/spec)
- Prepare quick rollback procedure.

Outputs:

- Rollout runbook and monitoring dashboard notes.

Exit criteria:

- Stabilization window passes without blocking regressions.

## Phase 7 (5%) - Hard cutover cleanup and closure

Goals:

- Remove legacy ask-default dependencies.
- Close migration with maintainable ownership boundaries.

Implementation checklist:

- Remove dead/temporary compatibility branches for ask V1 fallback where approved.
- Finalize docs: architecture, guard policy, rollout history, ownership.
- Keep only required rollback hooks if policy demands.

Outputs:

- Hard-cutover completion notes and final handoff.

Exit criteria:

- Ask lane defaults to V3 path and legacy path is no longer operationally required.

## 5. Suggested staffing split (for immediate task assignment)

If running in parallel, this split usually minimizes blocking:

- Squad A (Backend core, ~34%): Phase 1 + Phase 2 + backend part of Phase 4.
- Squad B (Frontend UX, ~28%): Phase 3 + frontend part of Phase 4.
- Squad C (Quality + rollout, ~25%): Phase 5 + Phase 6 (with support from A/B).
- Squad D (Closure, ~5%): Phase 7.
- Tech lead / integration buffer (~8%): Phase 0 and cross-phase decisions.

## 6. Critical dependencies and sequencing

1. Phase 0 must complete before implementation starts.
2. Phase 1 and Phase 2 should be completed before Phase 3 reaches integration.
3. Phase 4 starts once core lane path (Phase 1/3) is usable.
4. Phase 5 must be green before broad rollout in Phase 6.
5. Phase 7 starts only after rollout stabilization sign-off.
