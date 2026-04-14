# Render Optimization Docs

Status: Draft baseline for full-system optimization, with phase execution docs.

Last updated: 2026-04-14.

## Purpose

This folder defines a complete end-to-end optimization reference for thread execution and ask rendering performance in PlanningTreeMain (PTM).

The content is intentionally broad and detailed so we can:

- list every meaningful optimization lever
- discuss trade-offs clearly
- score and prioritize later without re-discovering context

## Primary documents

- `docs/render/render-optimization-comprehensive.md`
- `docs/render/phases/README.md`
- `docs/render/ask-migration-phases/README.md`
- `docs/render/ask-migration-phases/system-freeze/README.md`
- `docs/render/decision-pack-v1.md`
- `docs/render/system-freeze/README.md`

## What this includes

- current PTM bottleneck map (backend + transport + frontend + UI)
- detailed comparison vs CodexMonitor and Goose
- complete improvement catalog by layer
- workflow examples (before/after)
- metrics and test strategy
- rollout and safety strategy
- prioritization template for later filtering
- phase-by-phase execution docs (one file per phase)
- ask queue migration phase docs (execution -> ask parity)

## Current execution planning scope

The active phase execution plan intentionally focuses on Layer A-E only:

- backend ingest/projection/persistence
- SSE reliability/reconnect
- frontend state apply pipeline
- render/component performance
- data volume and queue UX flow

Temporarily excluded from this execution wave:

- Layer F (observability/profiling/test expansion)
- Layer G (rollout/safety program)

## Required Governance Check

Before implementing any phase, run:

```powershell
npm run check:render_freeze
```

The phase can proceed only when this check is PASS.
