# Phase 6 Validation

## Validation Rules
- Treat this file as the operational checklist for Phase 6 validation.
- Mark items complete only when code, tests, stress behavior, and replay behavior agree.
- Validate semantic convergence, not only apparent responsiveness.
- Do not mark cleanup safe while its enabling gate evidence is still missing.

## Cross-Subphase Validation
### Current Status
- Not started

### Baseline Expectations
- [ ] baseline performance evidence is recorded before optimization claims
- [ ] baseline replay and reconnect behavior is recorded before hardening claims
- [ ] migration-critical rollback boundaries are documented before cleanup begins

### Semantic Safety Expectations
- [ ] durable normalized state remains the replay source of truth
- [ ] no Phase 6 work redefines unresolved Phase 5 semantics
- [ ] performance changes preserve semantic equivalence
- [ ] reconnect hardening remains durable-store-first
- [ ] cleanup remains gate-based and rollback-aware

## Phase 6.1 Validation
### Current Status
- Not started

### Performance And Dense-Event Checks
- [ ] snapshot load latency has a recorded baseline
- [ ] event application has a recorded baseline
- [ ] render-model generation has a recorded baseline
- [ ] transcript rendering has a recorded baseline
- [ ] dense-event fixtures are defined and reproducible
- [ ] measured gains are compared against the same migrated path class
- [ ] optimized paths remain semantically identical to baseline behavior

## Phase 6.2 Validation
### Current Status
- Not started

### Concurrency And Replay Checks
- [ ] concurrent stream isolation is validated
- [ ] wrong-stream and wrong-thread attachment are prevented under stress
- [ ] cross-cancel does not occur under mixed activity
- [ ] reconnect under load remains correct
- [ ] guarded refresh remains recovery-only
- [ ] replay after refresh, reload, and restart is semantically faithful
- [ ] memory-only live state never becomes replay authority

## Phase 6.3 Validation
### Current Status
- Not started

### Cleanup Checks
- [ ] every cleanup target is classified before removal
- [ ] every removal names its replacement path
- [ ] every removal references exact enabling gate evidence
- [ ] every removal records rollback impact
- [ ] no removal proceeds while still blocked or uncertain
- [ ] post-removal verification proves the replacement path remains correct
- [ ] docs distinguish permanent architecture from removed transitional code
