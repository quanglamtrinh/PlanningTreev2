# Workflow Core V2 Boundary Docs

This directory now serves two purposes:

- The current boundary docs for the hard V4/Session Core V2 architecture.
- A historical archive of the phase plans used to reach that boundary.

Current boundary:

- Session Core V2 is the sole runtime/conversation surface under
  `/v4/session/*`; the legacy conversation runtime, chat-service, Codex-client,
  V3 thread stores, and V3 conversation components have been removed.
- Execution/audit workflow business logic is owned by Workflow Core V2 and V4
  workflow routes for the Breadcrumb V2 path.
- Active frontend workflow entry points use Workflow V2 state, events, and
  mutations.
- The current V2 workflow core owns workflow state, thread binding, context
  packets, execution/audit orchestration, events, artifact generation, and V4
  workflow routes. Product APIs are exposed under `/v4` only.

Documents:

- [Session and Workflow V2 Contract Freeze](./session-workflow-v2-contract.md)
  freezes the current boundary and target public rules.
- [Workflow V2 Roadmap](./workflow-v2-roadmap.md) breaks the migration into
  implementation phases and gate criteria.
- [Workflow Core V2 Architecture](./workflow-core-v2-architecture.md) describes
  the backend package, state ownership, orchestration boundaries, and adapter
  strategy.
- [Workflow V2 API Contract](./workflow-v2-api-contract.md) defines the target
  V4 workflow endpoints, request/response shapes, idempotency rules, and event
  stream.
- [Workflow V2 Cutover Checklist](./workflow-v2-cutover-checklist.md) gives the
  execution checklist, grep gates, test gates, rollback guidance, and risk
  register.
- [Phase 0 Gate Report](./phase-0-gate-report-v1.md) records the current hybrid
  audit, frozen contract decisions, blockers, and verification command for the
  contract-alignment phase.
- [Phase 6 Breadcrumb Cutover Plan](./phase-6-breadcrumb-v2-cutover-plan-v1.md)
  records the completed frontend cutover from the old workflow state/mutations to
  Workflow V2 while keeping Session Core V2 as the runtime surface.
- [Phase 7 End-to-End Workflow Actions Plan](./phase-7-end-to-end-workflow-actions-plan-v1.md)
  records the completed vertical slices and gates for proving ask, execution,
  audit, and package review actions end to end through Workflow V2 and Session
  Core V2.
- [Phase 8 Context Stale and Rebase Plan](./phase-8-context-stale-rebase-plan-v1.md)
  records the completed stale-context detection, dedicated context rebase route,
  UI rebase action, and verification gates for keeping long-lived Workflow V2
  threads aligned with updated source artifacts.
- [Phase 9 Artifact Orchestrator Alignment Plan](./phase-9-artifact-orchestrator-alignment-plan-v1.md)
  records the completed V2 ownership boundary for frame, clarify, spec, and split
  artifact workflows, including V4 routes, Workflow V2 events, and context
  freshness integration.
- [Phase 10 V3 Compatibility, Deprecation, and Removal Plan](./phase-10-v3-compatibility-deprecation-removal-plan-v1.md)
  is retained as historical context for the compatibility-removal work.

Migration rules:

- Keep `/v4/session/*` session-only. Do not add workflow business behavior to
  the session route layer.
- Keep business prompts, thread binding, context rebasing, and workflow action
  authorization in the backend.
- Do not reintroduce V3 conversation runtime, thread stores, or direct Codex
  client execution.
- Treat `thread/inject_items` support in Session Core V2 as an early blocker for
  thread binding and context packet delivery.
- Run `python scripts/check_workflow_v2_phase0.py` after changing these docs to
  keep the Phase 0 contract freeze coherent.
