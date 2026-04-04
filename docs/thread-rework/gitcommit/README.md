# Git Commit Rework

Primary planning docs for standardizing node commit metadata across split and execution/audit workflow:

- `docs/thread-rework/gitcommit/gitcommit-phased-roadmap.md`
- `docs/thread-rework/gitcommit/gitcommit-phase0-1-handoff.md`
- `docs/thread-rework/gitcommit/gitcommit-phase2-3-handoff.md`
- `docs/thread-rework/gitcommit/gitcommit-phase4-5-handoff.md`
- `docs/thread-rework/gitcommit/gitcommit-phase6-7-handoff.md`

Status:

- implemented through Phase 7 (rollout stabilization + cleanup closeout)

This directory is reserved for:

- commit trigger and persistence contract decisions
- phase-level implementation skeletons
- rollout and cleanup checklists for commit metadata in node describe

Operational scripts:

- `python scripts/gitcommit_phase6_smoke.py --repeat 2` (Phase 6 internal-stage smoke gate)
- `python scripts/check_gitcommit_phase7_cleanup.py` (Phase 7 cleanup contract guard)

Locked scope baseline:

- all active thread surfaces are V3 by-id
- no reset button changes in this track
- no historical backfill; apply only from rollout point forward
- `.planningtree` is allowed to be tracked and committed
- review prompt policy excludes scanning `.planningtree`
- split commits are recorded on the parent node being split
- execution-node commits are recorded on:
  - `Mark Done from Execution`
  - `Review in Audit`

Artifacts:

- `docs/thread-rework/gitcommit/artifacts/phase-6/*`
- `docs/thread-rework/gitcommit/artifacts/phase-7/*`
