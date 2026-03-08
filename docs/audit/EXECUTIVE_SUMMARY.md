# Executive Summary — PlanningTreeCodex Legacy Audit

Audit date: 2026-03-07
Audited project: `C:\Users\Thong\PlanningTree\PlanningTreeCodex`
Rebuild target: `C:\Users\Thong\PlanningTreeMain`

---

## What PlanningTreeCodex Is

PlanningTreeCodex is a local-first single-user prototype application that helps developers plan and execute complex multi-step tasks using an AI-assisted tree structure.

The core workflow:
1. Create a project and describe a large goal
2. Use AI to "split" the goal into a tree of sub-tasks (walking skeleton or slice mode)
3. Navigate the tree, view node details, chat with an AI agent per node
4. Optionally plan and execute "gates" (automated checkpoints)
5. Complete nodes, with rollback available when gates fail

The prototype works but is not distributable, has no auth, no deployment story, and carries significant structural debt from a feature set (gates, rollback, versions) that is being removed.

---

## Stack

Python/FastAPI backend + React/TypeScript frontend. No database — file-based JSON persistence. Server-Sent Events for real-time updates. Codex app server subprocess for AI operations. No auth, no deployment infrastructure.

---

## Key Metrics

| Metric | Value |
|---|---|
| Backend Python files | 68 |
| Largest file (backend) | orchestrator.py (~2,800 lines) |
| Largest file (frontend) | App.tsx, WorkflowGraph.tsx (~1,554 lines each) |
| CSS lines | 2,591 (single file) |
| API endpoints | 17 + 2 SSE streams |
| Audit event types | 26 |
| Theme variants | 5 |
| Test coverage (backend) | Partial (unit + some integration) |
| Test coverage (frontend) | Unit + E2E via Playwright |

---

## What the Rebuild Removes (~40% of the codebase)

The gate workflow, rollback, and version restore systems are being removed entirely from v1. These features account for approximately:
- ~40% of `orchestrator.py` (gate planning, gate running, rollback, version management)
- ~30% of `storage.py` (checkpoint management, version snapshots, audit writing)
- All of `split_graph.py` (LangGraph drift-retry complexity)
- All of `envelope.py` and `envelope_handlers.py` (gate output validation)
- All of `worker_adapter.py` gate config section
- `VersionNavigator.tsx`, `ReconfirmationPanel.tsx`, `ContextLens.tsx` (UI components)
- Audit event system (26 event types, SSE stream, `store.ts`)

This removal is the primary driver of the rebuild's cleanliness improvement.

---

## What the Rebuild Keeps (Adapted)

| Feature | What Changes |
|---|---|
| AI tree planning (walking_skeleton, slice) | Prompts adapted to `title/description` model; LangGraph removed; OpenAI Responses API directly |
| Chat per node | Codex app server subprocess kept; session model simplified |
| File-based JSON persistence | Schema simplified significantly (3 files instead of 8+) |
| ReactFlow graph UI | Migrated to @xyflow/react; gate actions removed; decomposed into smaller components |
| SSE streaming (chat only) | Kept for chat; audit SSE removed |
| 5 theme CSS system | Kept; migrated to CSS Modules |
| Status model | Renamed and simplified: locked/draft/ready/in_progress/done |

---

## What the Rebuild Adds

| Feature | Description |
|---|---|
| npx launcher | `npx planningtree` entry point via PyInstaller bundled binary |
| Cloud auth | Identity + license only; no project data in cloud |
| Finish Task (redesigned) | Client-side action opening Breadcrumb Chat with prefilled draft |
| Mark Done | Explicit completion with sibling unlock |
| Sibling unlock | Sequential execution: completing a node unlocks next sibling |
| Workspace selection | First-run UI + config/app.json persistence |
| Bootstrap endpoint | App readiness check |
| Settings endpoint | Workspace config read/write |

---

## Primary Technical Debt Targets

1. **orchestrator.py (2,800 lines)** — god object; split into 5 focused service modules
2. **App.tsx (1,554 lines)** — all state in one component; decompose into Zustand stores + React Router
3. **WorkflowGraph.tsx (1,554 lines)** — decompose into 4 components
4. **styles.css (2,591 lines)** — global CSS; migrate to CSS Modules per component
5. **storage.py (1,200 lines)** — remove audit/version/checkpoint logic; simplify to ~400 lines
6. **No auth** — critical gap for any distribution

---

## Rebuild Strategy

**Clean break.** No in-place migration. No data migration from legacy storage format.

The rebuild uses `PlanningTreeCodex` only as a reference — for prompt templates, graph layout patterns, SSE streaming patterns, and Codex subprocess integration. The rebuild does not copy messy code.

Canonical rebuild specifications are in `PlanningTreeCodex/docs/` (10 spec files). These are the implementation source of truth. The legacy codebase is a reference, not a target.

---

## Phase Readiness

| Phase | Status |
|---|---|
| Phase 0: Context and goals | Complete |
| Phase 1: Audit documentation | **Complete (this document set)** |
| Phase 2: Design + Scaffold | Ready to begin |
| Phase 3: Core Graph + Project State | Pending Phase 2 |
| Phase 4: Breadcrumb Execution | Pending Phase 3 |
| Phase 5: AI Planning Modes | Pending Phase 4 |
| Phase 6: Polish + Packaging | Pending Phase 5 |

---

## Key Decisions Made

| Decision | Choice |
|---|---|
| Backend language | Python (keep) |
| Distribution | PyInstaller bundled binary via npm postinstall |
| Split AI | OpenAI Responses API directly (configurable model, default GPT-4o) |
| Chat AI | Codex app server subprocess (unchanged pattern) |
| Frontend framework | React 18 + TypeScript (keep) |
| Graph library | @xyflow/react (upgrade from reactflow 11) |
| State management | Zustand (new; replaces monolithic App.tsx state) |
| CSS approach | CSS Modules (replace global styles.css) |
| SSE (chat) | Keep (same pattern) |
| SSE (audit) | Remove (no project-wide event stream in rebuild) |
