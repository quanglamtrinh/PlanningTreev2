# Phase 04 Evidence Folder

Purpose:

- store benchmark and recovery fault-injection artifacts for Phase 04 gates

Canonical gate output:

- `docs/render/phases/phase-04-inmemory-actor-checkpointing/evidence/phase04-gate-report.json`

Required evidence files during gate evaluation:

- `backend-runtime-benchmark.json`
- `recovery-fault-injection.json`
- `phase04-gate-report.json`

Templates:

- `templates/backend-runtime-benchmark.template.json`
- `templates/recovery-fault-injection.template.json`

Gate report command:

```powershell
python scripts/phase04_gate_report.py `
  --benchmark docs/render/phases/phase-04-inmemory-actor-checkpointing/evidence/backend-runtime-benchmark.json `
  --recovery docs/render/phases/phase-04-inmemory-actor-checkpointing/evidence/recovery-fault-injection.json `
  --out docs/render/phases/phase-04-inmemory-actor-checkpointing/evidence/phase04-gate-report.json
```
