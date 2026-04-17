# Ask Migration System Freeze Pack (v1)

Status: Active governance pack.

Last updated: 2026-04-14.

## Purpose

This folder defines enforceable contracts, phase dependencies, and gate targets for the ask queue migration wave.

## Authority Order

1. docs/render/ask-migration-phases/README.md
2. artifacts in this folder (system-freeze)
3. phase docs in docs/render/ask-migration-phases/phase-a*/README.md

If there is a conflict, higher authority wins.

## Contents

- contracts/
  - AQC0-AQC7 contract definitions
- phase-manifest-v1.json
  - authoritative dependency graph and phase entry criteria
- phase-gates-v1.json
  - numeric pass/fail targets per phase

## Operational Rule

Before starting each phase:

1. confirm entry criteria in phase-manifest-v1.json
2. confirm gate targets in phase-gates-v1.json
3. confirm required frozen contract docs in contracts/
4. attach candidate-backed evidence under phase evidence/
