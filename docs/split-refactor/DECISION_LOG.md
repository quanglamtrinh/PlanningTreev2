# Split Refactor Decision Log

Last updated: 2026-03-17

## D-001: Canonical mode set

- Date: 2026-03-17
- Decision: The supported split mode set is exactly `workflow`, `simplify_workflow`, `phase_breakdown`, and `agent_breakdown`.
- Rationale: The refactor is a hard cutover to a smaller, explicit contract with one shared output family.

## D-002: Cutover policy

- Date: 2026-03-17
- Decision: This effort is a contract replacement, not a dual-mode compatibility campaign.
- Rationale: The primary goal is to remove old split contract assumptions instead of carrying both contracts forward indefinitely.

## D-003: API invalid-mode behavior

- Date: 2026-03-17
- Decision: Route-level bad mode handling must remain `400 invalid_request` even after the mode contract is closed over the 4 canonical modes.
- Rationale: The repo already treats invalid split mode as an application error contract. Refactoring must not silently drift to framework-default `422`.

## D-004: UI split entrypoint

- Date: 2026-03-17
- Decision: GraphNode menu is the sole split entrypoint after cleanup.
- Rationale: It is the verified live split surface and has the smallest blast radius for the UI cutover.

## D-005: split_metadata policy

- Date: 2026-03-17
- Decision: `split_metadata` must distinguish stable compatibility fields from debug-scoped raw payload.
- Rationale: Replay and UI need a normalized materialization record, while debug payload shape must remain non-authoritative.
