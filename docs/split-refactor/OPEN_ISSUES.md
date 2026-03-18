# Split Refactor Open Issues

Last updated: 2026-03-17

This file tracks unresolved product, cutover, or migration risks only.

## OI-001: Existing persisted old-mode data impact is unknown

- Status: open
- Risk: Historical snapshots, events, or replay surfaces may still contain `walking_skeleton` or `slice`.
- Why it matters: This refactor does not promise legacy compatibility by default, but unexpected old data in real projects could turn into a cutover blocker.
- Required resolution: If implementation spikes show real breakage that matters, record and approve an explicit migration or cutover follow-up rather than reintroducing legacy support ad hoc.

## OI-002: Stale docs may outlive the code cutover

- Status: open
- Risk: Some architecture and audit docs still describe split flow through `GraphControls` or `routes/nodes.py`.
- Why it matters: The refactor is explicitly changing ownership and entrypoint expectations, so stale docs can cause future drift.
- Required resolution: Update or annotate stale docs during Phase 6 or Phase 8 once the final ownership model is implemented.
