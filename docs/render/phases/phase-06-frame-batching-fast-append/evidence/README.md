# Phase 06 Evidence Folder

Purpose:

- store frontend batching and apply-order measurement artifacts for Phase 06 gates.

Canonical gate output:

- `docs/render/phases/phase-06-frame-batching-fast-append/evidence/phase06-gate-report.json`.

Required evidence files during gate evaluation:

- `frontend-event-burst-scenario.json`.
- `interactive-stream-smoke.json`.
- `apply-order-integration-tests.json`.
- `phase06-gate-report.json`.

Bootstrap sample files:

- this folder includes starter sample JSON for the three gate sources above so the gate command can dry-run immediately.

Templates:

- `templates/frontend-event-burst-scenario.template.json`.
- `templates/interactive-stream-smoke.template.json`.
- `templates/apply-order-integration-tests.template.json`.
- `templates/phase06-gate-report.template.json`.

Gate command:

```powershell
python scripts/phase06_gate_report.py `
  --burst docs/render/phases/phase-06-frame-batching-fast-append/evidence/frontend-event-burst-scenario.json `
  --interactive docs/render/phases/phase-06-frame-batching-fast-append/evidence/interactive-stream-smoke.json `
  --order docs/render/phases/phase-06-frame-batching-fast-append/evidence/apply-order-integration-tests.json `
  --out docs/render/phases/phase-06-frame-batching-fast-append/evidence/phase06-gate-report.json
```
