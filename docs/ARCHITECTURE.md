# Architecture - PlanningTree

Last updated: 2026-04-29

## Overview

PlanningTree is a local-first single-user app that serves a React frontend and a FastAPI backend from one local process.

## Current User-Facing Surfaces

- Graph workspace at `/`
- Breadcrumb chat at `/projects/:projectId/nodes/:nodeId/chat`
- AI split actions inside the graph node menu

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Backend | FastAPI + Pydantic | V4 HTTP API + SSE |
| Frontend | React 18 + TypeScript | Vite build, CSS Modules |
| State | Zustand | Project, graph, and UI state |
| Graph | `@xyflow/react` | Tree rendering |
| Persistence | File-based project/workflow data + SQLite runtime journal | `meta.json`, `tree.json`, `.planningtree/workflow_core_v2/*`, Session Core V2 SQLite/journal |

## Public Backend Route Surface

- `GET /health`
- `GET /v4/bootstrap/status`
- `GET|POST /v4/projects`
- `POST /v4/projects/attach`
- `GET /v4/projects/{project_id}/snapshot`
- `POST /v4/projects/{project_id}/reset-to-root`
- `DELETE /v4/projects/{project_id}`
- `PATCH /v4/projects/{project_id}/active-node`
- `POST /v4/projects/{project_id}/nodes`
- `PATCH /v4/projects/{project_id}/nodes/{node_id}`
- `/v4/projects/{project_id}/nodes/{node_id}/artifacts/*`
- `/v4/projects/{project_id}/nodes/{node_id}/workflow/*`
- `/v4/session/*`
- `GET /v4/usage/local`

## Persistence

Project data remains file-based under the app data root:

- `meta.json`
- `tree.json`
- `.planningtree/workflow_core_v2/{node_id}.json` for workflow state and node-level domain projections
- `.planningtree/workflow_core_v2/artifact_jobs.json` for project-level artifact job projections
- Session Core V2 SQLite/journal files for runtime event, turn, request, and rollout projections

Unsupported project layouts are rejected with `unsupported_project_layout`.

## Primary Flows

### Create And Manage Graph

1. User configures a base workspace root.
2. User creates or selects a project.
3. Backend returns a `tree.json` snapshot with inline node title/description.
4. User creates child nodes, edits node metadata, changes active selection, or resets to root.
5. Frontend re-renders the graph from the latest snapshot.

### Run AI Split

1. User picks one of the split modes from a graph node action menu.
2. Backend accepts the request through the V4 artifact orchestrator and starts an async split job through Session Core V2.
3. Frontend polls the V4 split artifact-job status until the job becomes `idle` or `failed`.
4. On success, frontend reloads the snapshot and shows the new child nodes.

### Breadcrumb Session

1. User clicks `Open Breadcrumb` or `Finish Task` in the graph.
2. Frontend navigates to `/projects/:projectId/nodes/:nodeId/chat`.
3. Breadcrumb view selects the Workflow Core V2 lane and Session Core V2 thread.
4. User sends a message through Session Core V2; backend starts a Codex JSON-RPC turn.
5. Runtime events are persisted in Session Core V2 and projected to the UI via SSE.

## Frontend Structure

- `frontend/src/features/graph/` owns the primary product surface.
- `frontend/src/features/conversation/` contains the Breadcrumb session/workflow UI.
- `frontend/src/features/session_v2/` owns the Session Core V2 runtime projection.
- `frontend/src/features/workflow_v2/` owns workflow V2 API/store/event clients.
- `frontend/src/stores/project-store.ts` owns project, snapshot, selection, and split polling state.
- `frontend/src/api/` owns route clients and shared types.

## Backend Structure

- `backend/routes/` defines the thin HTTP layer.
- `backend/services/` owns project/node/artifact service rules.
- `backend/business/workflow_v2/` owns workflow state, thread binding, artifact orchestration, execution, and audit.
- `backend/session_core_v2/` owns Codex JSON-RPC session runtime integration.
- `backend/storage/` owns atomic file persistence and Workflow Core V2 domain projections.

