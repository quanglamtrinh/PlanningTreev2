# Phase 05 Evidence Folder

Purpose:

- store persistence/broker/backpressure benchmark artifacts for Phase 05 gates.

Canonical gate output:

- `docs/render/phases/phase-05-persistence-broker-efficiency/evidence/phase05-gate-report.json`.

Required evidence files during gate evaluation:

- `persist-load-benchmark.json`.
- `broker-profile-run.json`.
- `slow-subscriber-stress.json`.
- `phase05-gate-report.json`.

Templates:

- `templates/persist-load-benchmark.template.json`.
- `templates/broker-profile-run.template.json`.
- `templates/slow-subscriber-stress.template.json`.
- `templates/phase05-gate-report.template.json`.

Gate commands:

```powershell
python scripts/phase05_persist_load_benchmark.py `
  --out docs/render/phases/phase-05-persistence-broker-efficiency/evidence/persist-load-benchmark.json

python scripts/phase05_broker_profile_run.py `
  --out docs/render/phases/phase-05-persistence-broker-efficiency/evidence/broker-profile-run.json

python scripts/phase05_slow_subscriber_stress.py `
  --out docs/render/phases/phase-05-persistence-broker-efficiency/evidence/slow-subscriber-stress.json

python scripts/phase05_gate_report.py `
  --persist docs/render/phases/phase-05-persistence-broker-efficiency/evidence/persist-load-benchmark.json `
  --broker docs/render/phases/phase-05-persistence-broker-efficiency/evidence/broker-profile-run.json `
  --slow docs/render/phases/phase-05-persistence-broker-efficiency/evidence/slow-subscriber-stress.json `
  --out docs/render/phases/phase-05-persistence-broker-efficiency/evidence/phase05-gate-report.json
```
