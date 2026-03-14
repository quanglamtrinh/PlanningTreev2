# Phase F: Frontend Document Workflow Completion

Last updated: 2026-03-12

## Goal

Complete the node-model roadmap by moving the frontend onto canonical node documents end-to-end and exposing lifecycle-aware task, briefing, spec, and AI generation flows in the UI.

## Delivered

### Frontend contracts and state

- added typed frontend `NodeState` and `SpecGenerationStatus`
- typed document and confirmation responses in the API client
- added frontend store actions for `updateNodeTask()` and `generateNodeSpec()`
- generation failures now re-sync snapshot and documents so `spec_generation_status=failed` is reflected immediately

### Document panels and lifecycle UI

- added reusable `TaskPanel`
- added shared lifecycle summary rendering for task, briefing, and spec panels
- breadcrumb tab order is now `Planning`, `Task`, `Ask`, `Briefing`, `Spec`, `Execution`
- renamed the old `info` concept to `briefing` while keeping route-state alias compatibility for `info`

### Graph workflow migration

- graph detail overlay now uses the compact task panel instead of the legacy title/description editor
- active frontend task editing now goes through `PUT /documents/task`
- graph-to-breadcrumb routing is phase-aware:
  - `planning -> task`
  - `briefing_review -> briefing`
  - `spec_review -> spec`
  - `ready_for_execution` / `executing -> execution`
- composer seeding now happens only when routing into the execution tab

### Spec generation UI

- spec panel now exposes `Generate Spec` / `Regenerate Spec`
- UI reflects `idle`, `generating`, and `failed` generation states
- regenerating a ready-for-execution node visibly steps the UI back to spec review after refresh

## Verification

- `npm run test:unit`
- `npm run build`

## Follow-up

The node-model roadmap described in the implementation checklist is now complete. Future work, if any, should be planned as new feature work rather than as remaining node-model phase debt.
