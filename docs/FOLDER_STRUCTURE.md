# Folder Structure - PlanningTree Rebuild

Version: 0.2.0-phase-c
Last updated: 2026-03-12

## Ownership Rules

- each directory has a single clear owner
- business logic lives in `backend/services/`
- filesystem access lives in `backend/storage/`
- HTTP handling lives in `backend/routes/`
- frontend feature code stays under `frontend/src/features/`

## High-Level Layout

```text
PlanningTreeMain/
  backend/
  frontend/
  launcher/
  scripts/
  docs/
```

## Backend

```text
backend/
  main.py
  ai/
    codex_client.py
    openai_client.py
    split_context_builder.py
    split_prompt_builder.py
  config/
    app_config.py
  errors/
    app_errors.py
  routes/
    auth.py
    bootstrap.py
    chat.py
    nodes.py
    projects.py
    settings.py
  services/
    ask_service.py
    chat_service.py
    node_service.py
    node_task_fields.py
    project_service.py
    snapshot_view_service.py
    split_service.py
    thread_service.py
    tree_service.py
  storage/
    chat_store.py
    config_store.py
    file_utils.py
    node_files.py
    node_store.py
    project_ids.py
    project_locks.py
    project_store.py
    storage.py
    thread_store.py
  tests/
    integration/
    unit/
```

## Frontend

```text
frontend/
  src/
    api/
    components/
    features/
    stores/
    styles/
```

## Project Data on Disk

```text
<app-data-root>/
  config/
    app.json
    auth.json
  projects/
    <project-id>/
      meta.json
      tree.json
      thread_state.json
      chat_state.json
      nodes/
        <node-id>/
          task.md
          briefing.md
          spec.md
          state.yaml
```

## Notes

- `project_store.py` owns project-level files such as `meta.json` and `tree.json`
- `node_store.py` owns per-node document files
- `thread_store.py` and `chat_store.py` own thread/chat runtime state
- public snapshots are assembled from `tree.json` plus per-node documents
