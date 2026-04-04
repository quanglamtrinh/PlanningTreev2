# Phase 6 Smoke Results

Date: 2026-04-04  
Window: post-cutover observe-only validation.

## Automated smoke evidence

Frontend:

```bash
npm --prefix frontend run typecheck
npm --prefix frontend run test:unit -- tests/unit/MessagesV3.test.tsx tests/unit/applyThreadEventV3.test.ts
```

Result:

- PASS: typecheck
- PASS: targeted unit tests (`34 passed`, `186 tests`)

Backend:

```bash
python -m pytest -q backend/tests/unit/test_execution_audit_workflow_service.py backend/tests/unit/test_conversation_v2_projector.py backend/tests/unit/test_conversation_v3_projector.py backend/tests/unit/test_conversation_v3_fileschanged_parity_fixtures.py
python -m pytest -q backend/tests/integration/test_phase5_execution_audit_rehearsal.py backend/tests/integration/test_phase6_execution_audit_cutover.py
```

Result:

- PASS: targeted unit suite (`27 passed`)
- PASS: strict integration suite (`3 passed`)

## Manual smoke matrix

| Scenario | Expected | Result |
|---|---|---|
| New execution turn with semantic fileChange and real diff | Expand shows patch rows and non-zero `+/-` stats | PASS |
| New execution turn commandExecution only | Renders command card, not inferred file-change card | PASS |
| Legacy/path-only payload with no canonical diff | Fallback remains minimal, no synthetic `+0/-0` stats | PASS |
| Audit lane semantic fileChange diff | Uses same file-change renderer semantics as execution | PASS |

## Notes

- React Router future-flag warnings remain visible in dev/test logs and are not part of file-change migration scope.
- No runtime gating was needed for the cutover window.
