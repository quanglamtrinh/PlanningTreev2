# Workflow V2 Migration Docs

This directory tracks the migration from the current hybrid architecture to a
Workflow Core V2 owned business workflow plane.

Current boundary:

- Session Core V2 is the native runtime/conversation surface under
  `/v4/session/*`.
- Execution/audit workflow business logic is still owned by the V3 workflow
  service and exposed to the new Breadcrumb UI through V3 state/mutations.
- The migration target is a V2 workflow core that owns workflow state, thread
  binding, context packets, execution/audit orchestration, events, and V4
  workflow routes. V3 routes become compatibility adapters.

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

Migration rules:

- Keep `/v4/session/*` session-only. Do not add workflow business behavior to
  the session route layer.
- Keep business prompts, thread binding, context rebasing, and workflow action
  authorization in the backend.
- Do not remove V3 during the migration. First make V3 a thin adapter over
  Workflow Core V2, then deprecate or remove it after the new UI path no longer
  imports V3 workflow code.
- Treat `thread/inject_items` support in Session Core V2 as an early blocker for
  thread binding and context packet delivery.
- Run `python scripts/check_workflow_v2_phase0.py` after changing these docs to
  keep the Phase 0 contract freeze coherent.
