# Node Data Model - Implementation Checklist

## Current State

**Active Phase**: Phase F complete, roadmap complete  
**Last Updated**: 2026-03-12  
**Spec Reference**: [NODE_MODEL_SPEC.md](NODE_MODEL_SPEC.md)  
**Plan Reference**: [PHASE_F_PLAN.md](PHASE_F_PLAN.md)

## Completed Through Phase F

### Phase A: Storage Layer

- [x] Add canonical markdown and YAML parsers/renderers for node documents
- [x] Add `NodeStore` project-aware CRUD for `task.md`, `briefing.md`, `spec.md`, and `state.yaml`
- [x] Add atomic text writes and storage wiring
- [x] Add unit coverage for node file parsing, validation, and directory creation

### Phase B: Tree Index Migration

- [x] Replace monolithic `state.json` runtime storage with `tree.json` plus per-node directories
- [x] Move internal tree storage to `tree_state.node_index`
- [x] Introduce `node_kind` and remove internal reliance on `is_superseded`
- [x] Add migration from v3 projects and fail-fast validation for missing node files
- [x] Keep public snapshot compatibility through `node_registry`
- [x] Keep synced caches in `tree.json` for `phase` and thread/chat identifiers

### Phase C: Document Authority and CRUD

- [x] Persist `tree.json` as schema v5
- [x] Strip `title` and `description` from persisted `tree.json`
- [x] Add v4 -> v5 migration and persistence normalization
- [x] Keep `task.md`, `briefing.md`, `spec.md`, and `state.yaml` as authoritative node documents
- [x] Add node document service methods:
  `get_documents()`, `get_task()`, `get_briefing()`, `get_spec()`, `get_state()`,
  `update_task()`, `update_briefing()`, `update_spec()`
- [x] Add document routes:
  - `GET /projects/{pid}/nodes/{nid}/documents`
  - `GET /projects/{pid}/nodes/{nid}/documents/task`
  - `PUT /projects/{pid}/nodes/{nid}/documents/task`
  - `GET /projects/{pid}/nodes/{nid}/documents/briefing`
  - `PUT /projects/{pid}/nodes/{nid}/documents/briefing`
  - `GET /projects/{pid}/nodes/{nid}/documents/spec`
  - `PUT /projects/{pid}/nodes/{nid}/documents/spec`
  - `GET /projects/{pid}/nodes/{nid}/documents/state`
- [x] Keep `PATCH /projects/{pid}/nodes/{nid}` as a backward-compatible bridge to `task.md`
- [x] Backfill public snapshot `title` and `description` from `task.md`
- [x] Add shared task-field enrichment for split, ask, chat, and thread context paths
- [x] Append merged clarification packets into `briefing.md` clarified answers as a best-effort copy

### Phase D: Phase Lifecycle and Confirmation

- [x] Add confirmation endpoints for task, briefing, and spec
- [x] Add explicit execution-start lifecycle route
- [x] Implement phase advancement across `planning -> briefing_review -> spec_review -> ready_for_execution -> executing -> closed`
- [x] Implement automatic phase step-back and downstream confirmation reset when confirmed documents change
- [x] Track spec existence through `state.yaml.spec_generated`
- [x] Add dedicated lifecycle/confirmation and execution-guard test coverage

### Phase E: Spec Generation

- [x] Add spec prompt builder and spec generation service
- [x] Add route for explicit AI spec generation
- [x] Persist generated spec into `spec.md`
- [x] Add `state.yaml.spec_generation_status` with restart recovery for stranded generation
- [x] Reuse lifecycle-aware spec persistence so regenerated confirmed specs step back to `spec_review`
- [x] Add unit and integration coverage for generation success, retry, failure, and guards

### Phase F: Frontend Document Workflow

- [x] Replace the remaining legacy task editor with reusable task, briefing, and spec panels
- [x] Move active frontend task editing from legacy `PATCH /nodes/{id}` calls to document endpoints
- [x] Add typed frontend node state plus lifecycle summaries in task/briefing/spec panels
- [x] Expose AI spec generation in the spec panel, including `idle | generating | failed` UI states
- [x] Replace the graph detail overlay with compact task-document editing and phase-aware breadcrumb routing
- [x] Add frontend unit coverage for task/spec panels, store actions, and graph-to-breadcrumb routing

## Verification Completed

- [x] Backend test suite passes: `python -m pytest backend/tests -q`
- [x] Frontend unit test suite passes: `npm run test:unit`
- [x] Frontend production build passes: `npm run build`
- [x] Document CRUD unit coverage added
- [x] Document endpoint integration coverage added
- [x] Migration coverage updated for v3 -> v5 and v4 -> v5
- [x] Split, ask, snapshot, and node-service tests updated for schema v5 behavior
- [x] Lifecycle phase-transition and auto-unconfirm unit coverage added
- [x] Confirmation endpoint integration coverage added
- [x] Execution-start and completion guard coverage added
- [x] Spec prompt-builder unit coverage added
- [x] Spec generation service unit coverage added
- [x] Spec generation route integration coverage added
- [x] Task panel unit coverage added
- [x] Spec panel generation UI coverage added
- [x] Graph routing and document-panel frontend coverage added

## Current Phase F Rules

- [x] `tree.json` is structural plus synced caches, not the source of task content
- [x] Persisted nodes do not store `title` or `description`
- [x] Empty document update payloads return `400`
- [x] Superseded or `done` nodes reject document edits, confirmation, and execution start with `409`
- [x] All document edits reject while `phase=executing`
- [x] Task confirmation requires `phase=planning` plus non-empty title and purpose
- [x] Briefing confirmation requires `phase=briefing_review` and `task_confirmed=true`
- [x] Spec confirmation requires `phase=spec_review`, `briefing_confirmed=true`, and `spec_generated=true`
- [x] Content-changing edits to confirmed task/briefing/spec documents clear downstream confirmations and step phase back
- [x] AI spec generation is allowed only from `spec_review` or `ready_for_execution`
- [x] Successful AI generation replaces the full `spec.md`, sets `spec_generated=true`, and leaves `spec_generation_status=idle`
- [x] Failed AI generation leaves `spec.md` unchanged and sets `spec_generation_status=failed`
- [x] Startup recovery downgrades stranded `spec_generation_status=generating` to `failed`
- [x] `state.yaml` remains read-only through HTTP
- [x] Shipping frontend task editing uses `PUT /documents/task` instead of legacy `PATCH /nodes/{id}`
- [x] Breadcrumb workspace exposes `Planning`, `Task`, `Ask`, `Briefing`, `Spec`, and `Execution`
- [x] Task, briefing, and spec panels show lifecycle-aware summaries instead of raw state editing
- [x] Graph detail editing uses the compact task panel and graph-to-breadcrumb routing follows node phase
- [x] Spec panel exposes `Generate Spec` / `Regenerate Spec` and renders `idle | generating | failed` generation state

## Remaining Work

### Node-Model Roadmap

- [x] No remaining phase work in the current node-model roadmap

## Notes

- Public snapshot compatibility is intentional: frontend consumers still receive `title` and `description`
- Persisted `tree.json` normalization prevents legacy caches from reappearing after save
- This file is now the implementation status source, while [PHASE_C_PLAN.md](PHASE_C_PLAN.md), [PHASE_D_PLAN.md](PHASE_D_PLAN.md), [PHASE_E_PLAN.md](PHASE_E_PLAN.md), and [PHASE_F_PLAN.md](PHASE_F_PLAN.md) remain delivery records
