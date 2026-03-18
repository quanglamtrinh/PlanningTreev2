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

## D-006: Temporary legacy route bridge for Phase 1

- Date: 2026-03-17
- Decision: `walking_skeleton` and `slice` remain temporarily accepted at the `/split` route during Phase 1 through the pre-cutover phases.
- Rationale: The current runtime still depends on those modes, so the route boundary must be closed without breaking the existing split path before later phases land.

## D-007: Split prompt builders are separated by contract generation

- Date: 2026-03-17
- Decision: `backend/ai/split_prompt_builder.py` is canonical-only for the 4 new modes, while old `walking_skeleton` and `slice` behavior lives in `backend/ai/legacy_split_prompt_builder.py` during the bridge period.
- Rationale: The canonical flat contract must be isolated from legacy payload shapes so prompt/schema evolution does not keep reintroducing old-mode assumptions into the new split pipeline.

## D-008: Canonical payload parsing is strict and non-aliasing

- Date: 2026-03-17
- Decision: Canonical parsing accepts only `subtasks[{id,title,objective,why_now}]`, preserves list order, and does not remap legacy keys such as `prompt`, `risk_reason`, or `what_unblocks`.
- Rationale: Later service materialization must depend only on the shared flat contract rather than permissive key aliasing that would effectively preserve multiple payload contracts.
