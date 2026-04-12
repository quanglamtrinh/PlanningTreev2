# Phase 01 Preflight Checklist (v1)

Status: Required before Phase 01 implementation begins.

## GO/NO-GO Conditions

Phase 01 is `GO` only if all checks below are true.

## A. Governance Artifacts

- [ ] `docs/render/decision-pack-v1.md` exists and is approved.
- [ ] `docs/render/system-freeze/phase-manifest-v1.json` exists.
- [ ] `docs/render/system-freeze/phase-gates-v1.json` exists.
- [ ] `docs/render/system-freeze/contracts/c1-event-stream-contract-v1.md` exists.
- [ ] `docs/render/system-freeze/contracts/c2-replay-resync-contract-v1.md` exists.

## B. Contract Definitions

- [ ] C1 envelope schema file exists and is valid JSON.
- [ ] C1 bridge policy defines legacy-to-canonical mapping.
- [ ] C2 replay-gap mismatch behavior is explicit.
- [ ] Heartbeat cursor rule is explicit and testable.

## C. Validation and Consistency

- [ ] `python scripts/validate_render_freeze.py` passes.
- [ ] Phase 01 README references C1/C2 and Decision Pack alignment.
- [ ] Subphase template references Decision Pack alignment.

## D. Phase 01 Design Note

- [ ] Phase 01 implementation note exists in `phase-01/subphases/`.
- [ ] Gate IDs `P01-G1..P01-G3` are included in the note.
- [ ] Measurement method for each gate is documented.

## E. Test Readiness

- [ ] Contract compatibility tests are identified and named.
- [ ] Heartbeat cursor pollution test case exists.
- [ ] Replay boundary duplicate check case exists.

## Final Decision

- If any box is unchecked: `NO-GO`.
- If all boxes are checked: `GO`.

