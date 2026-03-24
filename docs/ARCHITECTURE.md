# Architecture - PlanningTree

Last updated: 2026-03-20

## Overview

PlanningTree is a local-first single-user app that serves a React frontend and a FastAPI backend from one local process.

## Current User-Facing Surfaces

- Graph workspace at `/`
- Breadcrumb chat at `/projects/:projectId/nodes/:nodeId/chat`
- AI split actions inside the graph node menu

## Tech Stack

| Layer | Technology | Notes |
|---|---|---|
| Backend | FastAPI + Pydantic | REST API only |
| Frontend | React 18 + TypeScript | Vite build, CSS Modules |
| State | Zustand | Project, graph, and UI state |
| Graph | `@xyflow/react` | Tree rendering |
| Persistence | File-based project data | `meta.json`, `tree.json`, lazy `split_state.json`, and `chat/{node_id}.json` |

## Public Backend Route Surface

- `GET /health`
- `GET /v1/bootstrap/status`
- `GET|PATCH /v1/settings/workspace`
- `GET|POST /v1/projects`
- `GET /v1/projects/{project_id}/snapshot`
- `POST /v1/projects/{project_id}/reset-to-root`
- `DELETE /v1/projects/{project_id}`
- `PATCH /v1/projects/{project_id}/active-node`
- `POST /v1/projects/{project_id}/nodes`
- `PATCH /v1/projects/{project_id}/nodes/{node_id}`
- `POST /v1/projects/{project_id}/nodes/{node_id}/split`
- `GET /v1/projects/{project_id}/split-status`
- `GET /v1/projects/{project_id}/nodes/{node_id}/chat/session`
- `POST /v1/projects/{project_id}/nodes/{node_id}/chat/message`
- `POST /v1/projects/{project_id}/nodes/{node_id}/chat/reset`
- `GET /v1/projects/{project_id}/nodes/{node_id}/chat/events` (SSE)

## Persistence

Project data remains file-based under the app data root:

- `meta.json`
- `tree.json`
- `split_state.json` after the first split run
- `chat/{node_id}.json` per-node chat sessions (lazy, created on first message)

Older project layouts are rejected with `legacy_project_unsupported`.

## Primary Flows

### Create And Manage Graph

1. User configures a base workspace root.
2. User creates or selects a project.
3. Backend returns a `tree.json` snapshot with inline node title/description.
4. User creates child nodes, edits node metadata, changes active selection, or resets to root.
5. Frontend re-renders the graph from the latest snapshot.

### Run AI Split

1. User picks one of the split modes from a graph node action menu.
2. Backend accepts the request and starts an async split job on the project-shared Codex thread.
3. Frontend polls `GET /split-status` until the job becomes `idle` or `failed`.
4. On success, frontend reloads the snapshot and shows the new child nodes.

### Breadcrumb Chat

1. User clicks `Open Breadcrumb` or `Finish Task` in the graph.
2. Frontend navigates to `/projects/:projectId/nodes/:nodeId/chat`.
3. Chat view loads session from backend, opens SSE event stream.
4. User sends a message; backend creates a Codex turn in a background thread.
5. Streaming deltas arrive via SSE; completed text is persisted to `chat/{node_id}.json`.

## Frontend Structure

- `frontend/src/features/graph/` owns the primary product surface.
- `frontend/src/features/breadcrumb/` contains the breadcrumb chat UI.
- `frontend/src/stores/project-store.ts` owns project, snapshot, selection, and split polling state.
- `frontend/src/api/` owns route clients and shared types.

## Backend Structure

- `backend/routes/` defines the thin HTTP layer.
- `backend/services/` owns graph CRUD and split business rules.
- `backend/storage/` owns atomic file persistence.

## Planned Model References

- Future thread and review model: [planned-thread-review-model.md](C:/Users/Thong/PlanningTreeMain/docs/reference/planned-thread-review-model.md)
