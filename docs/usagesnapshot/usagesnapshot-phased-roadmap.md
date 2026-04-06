# Usage Snapshot Phased Roadmap

Status: planning skeleton for implementation.

Last updated: 2026-04-06.

## 1. Scope and locked decisions

This roadmap assumes the following decisions are frozen:

- Usage Snapshot is a dedicated screen, not an inline expansion of existing sidebar footer usage.
- Screen entry point is a button above the existing sidebar usage block.
- Snapshot scope is all Codex sessions under Codex home.
- Workspace/project selector is out of scope.
- Data refresh strategy is polling (initial fetch + interval + manual refresh).
- Delivery must include backend, frontend, and automated tests (unit/integration/E2E).

## 2. Non-goals

- No redesign of existing codex account/rate-limit snapshot behavior.
- No replacement of `/v1/codex/events` SSE flow.
- No migration of historical data into a persistent usage database.
- No multi-user or remote aggregation in this track.
- No workspace-specific filter UI in this track.

## 3. Proposed target architecture

Backend:

- New usage scanner service in Python to parse `.jsonl` files under `$CODEX_HOME/sessions` (fallback `~/.codex/sessions`).
- New read-only route `GET /v1/codex/usage/local`.
- Service-level in-memory cache with short TTL and cache key by `days`.
- Structured logging for scan duration, files visited, files parsed, parse-fail counts.

Frontend:

- New route `/usage-snapshot`.
- New page component showing:
  - overview cards
  - last-7-day chart
  - top model chips
  - loading/empty/error states
  - manual refresh button
- Polling hook with request-generation guard.
- Sidebar button above existing usage section to navigate to `/usage-snapshot`.

Testing:

- Backend unit tests for parser edge cases and aggregation.
- Backend integration tests for route contract.
- Frontend unit tests for page and sidebar entrypoint.
- Frontend E2E test validating user flow from sidebar button to loaded usage screen.

## 4. Phase split and effort estimate

Total baseline effort: 100% (about 23 engineering days).

| Phase | Name | Effort % | Est. days | Primary owners |
|---|---|---:|---:|---|
| 0 | Contract freeze and boundaries | 8% | 2.0 | Tech lead + BE/FE lead |
| 1 | Backend scanner and API foundation | 22% | 5.0 | BE |
| 2 | Backend performance and observability | 14% | 3.0 | BE |
| 3 | Frontend route, screen, and polling | 20% | 4.5 | FE |
| 4 | Sidebar entrypoint and UX polish | 9% | 2.0 | FE |
| 5 | Automated test matrix and E2E | 19% | 4.5 | QA + BE + FE |
| 6 | Rollout and stabilization | 6% | 1.5 | BE + FE + QA |
| 7 | Cleanup and closeout | 2% | 0.5 | BE + FE |

## 5. Detailed phase skeleton

## Phase 0 (8%) - Contract freeze and boundaries

Goals:

- Freeze payload contract and UX boundary before coding.
- Freeze parser semantics and counting rules to avoid implementation drift.

Key outputs:

- API schema draft for `/v1/codex/usage/local`.
- Locked parser rules:
  - handling of `total_token_usage` and `last_token_usage`
  - token delta logic to prevent double count
  - agent run counting heuristic
  - agent active-time gap cap logic
- Locked frontend states: loading, empty, partial-error, stale-refresh.

Exit criteria:

- No open contract-level ambiguity remains.
- Phase 1 can implement without revisiting product decisions.

## Phase 1 (22%) - Backend scanner and API foundation

Goals:

- Implement local usage scanner service and route contract.
- Produce deterministic snapshot shape for frontend.

Key implementation slices:

- Add `LocalUsageSnapshotService` with:
  - day-key generation
  - session root discovery from Codex home
  - day-directory traversal
  - line parsing and aggregation
  - totals and top-model derivation
- Add `GET /v1/codex/usage/local?days=30`.
- Wire service into FastAPI app state.
- Add baseline unit + integration tests.

Exit criteria:

- Route returns stable snapshot JSON for real local data.
- Edge cases around malformed lines and missing fields are covered.

## Phase 2 (14%) - Backend performance and observability

Goals:

- Reduce scan overhead and improve debuggability.
- Ensure predictable latency under larger session history.

Key implementation slices:

- Add cache strategy:
  - short TTL (for example 30s)
  - cache key by `days`
  - lock-safe updates
- Add scan metrics logs:
  - files visited and parsed
  - parse errors
  - scan duration
  - cache hit/miss
- Add defensive guards:
  - max line length
  - timestamp parse fallbacks
  - invalid numeric coercion handling

Exit criteria:

- Repeated polling does not re-scan files every request.
- Scan behavior is observable and triage-ready.

## Phase 3 (20%) - Frontend route, screen, and polling

Goals:

- Ship feature-complete usage screen wired to backend API.

Key implementation slices:

- Add frontend types for local usage snapshot.
- Add API client call `getLocalUsageSnapshot(days)`.
- Add polling hook:
  - initial fetch on mount
  - interval refresh
  - manual refresh
  - request-generation stale response guard
- Add `/usage-snapshot` route and page component.
- Render cards, chart, top models, and empty/error/loading states.

Exit criteria:

- Usage screen loads from live backend and remains responsive.
- Polling and manual refresh behave predictably.

## Phase 4 (9%) - Sidebar entrypoint and UX polish

Goals:

- Integrate feature entrypoint into existing sidebar flow.
- Finalize micro-interactions and accessibility.

Key implementation slices:

- Add sidebar button above usage block.
- Navigate to `/usage-snapshot` and preserve app shell behavior.
- Add route-aware active state styling.
- Tune copy, spacing, and accessibility labels.

Exit criteria:

- User can discover and open Usage Snapshot from existing sidebar quickly.
- Navigation and visual hierarchy are stable across themes.

## Phase 5 (19%) - Automated test matrix and E2E

Goals:

- Harden behavior with deterministic tests across layers.

Key implementation slices:

- Backend unit tests:
  - token counting
  - delta handling
  - run/time counting
  - malformed input tolerance
- Backend integration tests:
  - route payload schema
  - `days` query behavior
- Frontend unit tests:
  - page rendering states
  - polling refresh transitions
  - sidebar button navigation
- Frontend E2E:
  - open app
  - click sidebar button
  - verify usage screen loads expected sections

Exit criteria:

- Required test matrix passes in CI.
- No unresolved deterministic failures on this feature path.

## Phase 6 (6%) - Rollout and stabilization

Goals:

- Deploy safely and monitor early regressions.

Key implementation slices:

- Add rollout checklist for release candidate.
- Add operational checks:
  - route health
  - scan latency budget
  - frontend error-rate checks
- Run stabilization window and collect notes.

Exit criteria:

- Feature is stable under normal desktop usage.
- No blocker-class issues remain open.

## Phase 7 (2%) - Cleanup and closeout

Goals:

- Finalize docs and remove temporary rollout-only workarounds.

Key implementation slices:

- Remove temporary debug logs not needed in steady state.
- Finalize closeout summary, residual risks, and ownership notes.
- Mark progress tracker complete.

Exit criteria:

- Track is operationally closed and maintainable.

## 6. Suggested staffing split for parallel execution

- Backend squad:
  - Phase 1 + Phase 2 + backend portions of Phase 5.
- Frontend squad:
  - Phase 3 + Phase 4 + frontend portions of Phase 5.
- QA squad:
  - Phase 5 + validation support for Phase 6.
- Tech lead:
  - Phase 0 alignment and Phase 7 closure.

## 7. Sequencing constraints

1. Phase 0 before all implementation phases.
2. Phase 1 before Phase 3 API integration.
3. Phase 2 before final performance sign-off in Phase 5.
4. Phase 5 gate before rollout in Phase 6.
5. Phase 7 only after stabilization closure in Phase 6.

## 8. Risk register and mitigations

Risk: scan latency grows with session history.

- Mitigation:
  - cache with TTL
  - day-bounded traversal
  - instrumentation on scan duration and files parsed

Risk: token double-count from mixed usage payloads.

- Mitigation:
  - explicit delta logic
  - parser unit tests for mixed `last` + `total` sequences

Risk: stale polling responses overwrite fresher state.

- Mitigation:
  - request-generation guard in polling hook

Risk: route discoverability is low.

- Mitigation:
  - prominent button placement above existing usage block
  - unit and E2E tests for entrypoint flow

Risk: feature scope creep (workspace filter, SSE, persistence).

- Mitigation:
  - explicit non-goals in this roadmap
  - defer expansions to follow-up tracks after Phase 7
