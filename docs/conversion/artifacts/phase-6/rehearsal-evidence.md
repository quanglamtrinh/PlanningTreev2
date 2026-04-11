# Phase 6 Rehearsal Evidence

Date: 2026-04-10  
Owner: BE Conversion Track

## Rehearsal Dataset

- Data root: `tmp/phase6_rehearsal/appdata`
- Manifest: `tmp/phase6_rehearsal/manifest.json`
- Projects:
  - `alpha`: V2-only execution/audit
  - `beta`: mixed V2 + existing V3 (skip-existing path)
  - `gamma`: V2-only execution reserved for disabled-mode check

## Commands Executed

1. Dry-run all projects

- `python -m backend.tools.migrate_conversation_v2_to_v3 --all-projects --dry-run --data-root tmp/phase6_rehearsal/appdata --report-json docs/conversion/artifacts/phase-6/reports/rehearsal-dry-run.json`

2. Apply wave 1 (alpha + beta only)

- `python -m backend.tools.migrate_conversation_v2_to_v3 --project-id e3b89d3460a146d1986767e242075db3 --project-id 7dd354e0f5af41fe95b1c6099208f68a --data-root tmp/phase6_rehearsal/appdata --report-json docs/conversion/artifacts/phase-6/reports/rehearsal-apply-wave1.json`

3. Apply rerun (idempotency proof)

- `python -m backend.tools.migrate_conversation_v2_to_v3 --project-id e3b89d3460a146d1986767e242075db3 --project-id 7dd354e0f5af41fe95b1c6099208f68a --data-root tmp/phase6_rehearsal/appdata --report-json docs/conversion/artifacts/phase-6/reports/rehearsal-apply-wave1-rerun.json`

4. Disabled bridge behavior check (`conversation_v3_missing`, HTTP 409)

- API: `GET /v3/projects/{project_id}/threads/by-id/{thread_id}?node_id={node_id}`
- Report output: `docs/conversion/artifacts/phase-6/reports/rehearsal-disabled-mode-check.json`

## Results Summary

- Dry-run report: `scanned=5`, `migrated=4`, `skip_existing=1`, `failed=0`
- Apply wave 1 report: `scanned=4`, `migrated=3`, `skip_existing=1`, `failed=0`
- Apply rerun report: `scanned=4`, `migrated=0`, `skip_existing=4`, `failed=0` (idempotent)
- Disabled-mode API check:
  - `status_code=409`
  - `error.code=conversation_v3_missing`
  - `error.details={}`

## Artifacts Produced

- `docs/conversion/artifacts/phase-6/reports/rehearsal-dry-run.json`
- `docs/conversion/artifacts/phase-6/reports/rehearsal-apply-wave1.json`
- `docs/conversion/artifacts/phase-6/reports/rehearsal-apply-wave1-rerun.json`
- `docs/conversion/artifacts/phase-6/reports/rehearsal-disabled-mode-check.json`

