# FilesChanged Rework

Primary planning docs for migrating execution `fileChange` rendering to a CodexMonitor-style `changes[]` model:

- `docs/thread-rework/fileschanged/fileschanged-phased-roadmap.md`
- `docs/thread-rework/fileschanged/fileschanged-phase0-1-handoff.md`
- `docs/thread-rework/fileschanged/fileschanged-phase2-3-handoff.md`
- `docs/thread-rework/fileschanged/fileschanged-phase4-5-handoff.md`
- `docs/thread-rework/fileschanged/fileschanged-phase6-7-handoff.md`

Execution parity fixtures (Phase 4 hardening):

- `docs/thread-rework/fileschanged/artifacts/execution-fileschanged-parity-fixtures.json`
- `docs/thread-rework/fileschanged/artifacts/phase4-5-parity-report.md`

This directory is reserved for:

- file-change contract and migration decisions
- phase-level implementation skeletons
- rollout and cleanup checklists for execution/audit threads

Locked scope baseline:

- migrate execution first
- apply new model to new turns only (no historical backfill)
- converge to CodexMonitor-style `changes[]` as canonical UI source
- keep temporary compatibility for legacy `outputFiles` during migration
