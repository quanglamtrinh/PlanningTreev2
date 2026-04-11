# Render Optimization Docs

Status: Draft baseline for full-system optimization.

Last updated: 2026-04-11.

## Purpose

This folder defines a complete end-to-end optimization reference for thread execution and ask rendering performance in PlanningTreeMain (PTM).

The content is intentionally broad and detailed so we can:

- list every meaningful optimization lever
- discuss trade-offs clearly
- score and prioritize later without re-discovering context

## Primary document

- `docs/render/render-optimization-comprehensive.md`

## What this includes

- current PTM bottleneck map (backend + transport + frontend + UI)
- detailed comparison vs CodexMonitor and Goose
- complete improvement catalog by layer
- workflow examples (before/after)
- metrics and test strategy
- rollout and safety strategy
- prioritization template for later filtering