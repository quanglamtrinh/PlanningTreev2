# Phase C: Schema v5 Document Authority for Nodes

Last updated: 2026-03-12

## Goal

Make per-node documents the authoritative source for node content while preserving backward compatibility for the current frontend and public snapshot payloads.

## Delivered

### Persistence and migration

- `tree.json` is now persisted as `schema_version: 5`
- `v3 -> v5` migration creates node files and strips legacy `title` / `description`
- `v4 -> v5` migration strips legacy `title` / `description` from existing `tree.json`
- snapshot save paths normalize away `title` / `description` even if old in-memory data still carries them
- `tree.json` continues to cache `phase` and thread/chat IDs as synced fields

### Authoritative document model

- `task.md` owns `title`, `purpose`, `responsibility`
- `briefing.md` owns `user_notes`, `business_context`, `technical_context`, `execution_context`, `clarified_answers`
- `spec.md` owns `business_contract`, `technical_contract`, `delivery_acceptance`, `assumptions`
- `state.yaml` owns machine state and thread/chat identifiers

### Runtime compatibility

- public snapshots still expose `title` and `description`
- `SnapshotViewService` backfills those fields from `task.md`
- shared task-field enrichment is used by snapshot, split, ask, chat, and thread lineage code paths
- legacy `PATCH /projects/{pid}/nodes/{nid}` still accepts `{ title?, description? }` and writes only to `task.md`

### Document CRUD API

- `GET /projects/{pid}/nodes/{nid}/documents`
- `GET /projects/{pid}/nodes/{nid}/documents/task`
- `PUT /projects/{pid}/nodes/{nid}/documents/task`
- `GET /projects/{pid}/nodes/{nid}/documents/briefing`
- `PUT /projects/{pid}/nodes/{nid}/documents/briefing`
- `GET /projects/{pid}/nodes/{nid}/documents/spec`
- `PUT /projects/{pid}/nodes/{nid}/documents/spec`
- `GET /projects/{pid}/nodes/{nid}/documents/state`

## Guard behavior

- all document writes reject superseded nodes
- all document writes reject `done` nodes
- empty update payloads are rejected with `400`
- `task.title` must remain non-empty when updated
- `spec.md` is additionally frozen when `phase=executing`

## Ask merge copy

After a clarification packet is successfully merged into the planning thread, the packet is also copied into `briefing.md` as a best-effort convenience mirror:

- existing clarified answers are preserved
- new entries are separated by `---`
- each merged entry is stored as a bold summary followed by the packet context text
- failures in this copy step are logged and do not roll back the thread merge

## Verification

- `python -m pytest backend/tests -q`
  Result: `246 passed`
- `npm run build` in `frontend/`
  Result: success

## Follow-up

Phase C only changes document authority and CRUD. Confirmation workflow, phase step-back logic, and AI spec generation remain future work under later phases.
