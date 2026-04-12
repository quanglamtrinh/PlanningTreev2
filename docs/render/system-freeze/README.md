# Render System Freeze Pack (v1)

Status: Active governance pack.

Last updated: 2026-04-12.

## Purpose

This folder turns optimization decisions into enforceable, machine-checkable artifacts so phases can execute without contract drift.

## Authority Order

1. `docs/render/decision-pack-v1.md`
2. artifacts in this folder (`system-freeze`)
3. phase docs in `docs/render/phases/`

If there is a conflict, higher authority wins.

## Contents

- `contracts/`:
  - C1-C6 canonical contract definitions
  - C1 envelope schema + legacy bridge policy
- `phase-manifest-v1.json`:
  - authoritative phase dependency graph and contract ownership
- `phase-gates-v1.json`:
  - numeric pass/fail targets by phase
- `phase-1-preflight-checklist-v1.md`:
  - required pre-start checklist for Phase 01

## Validation

Run:

```powershell
python scripts/validate_render_freeze.py
```

Expected result:

- all phase docs aligned with Decision Pack contracts
- all phases mapped in manifest + gate file
- subphase templates aligned with required governance text

## Operational Rule

Before starting each phase:

1. run freeze validator
2. confirm phase entry criteria in manifest
3. confirm phase gates in gate file
4. create/update phase technical design note with implementation-specific values

