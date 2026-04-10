# Conversion Artifacts

This directory stores evidence and operational documentation for each conversion phase.

## Principles

- Each artifact must map to a phase in `docs/conversion/progress.yaml`.
- Artifacts should include creation date, owner, and command/test evidence.
- Do not overwrite old artifacts silently; if updated, include a clear revision changelog.

## Structure

- `phase-0/`: behavior matrix, policy matrix, decision log, open questions
- `phase-1/`: storage schema notes
- `phase-2/`: runtime sequence + event contract notes
- `phase-3/`: route cutover diff + compatibility notes
- `phase-4/`: service call graph + parity report
- `phase-5/`: frontend migration checklist + regression notes
- `phase-6/`: migration runbook + migration reports
- `phase-7/`: deletion log + deprecation notice
- `phase-8/`: smoke/stabilization/closeout evidence
