# Phase 7 Cleanup Checklist (Compat Harden)

Date: 2026-04-04  
Scope: harden canonical-first behavior while retaining wire compatibility fields in this cycle.

## Frontend cleanup

- [x] Removed command-text heuristic that inferred `fileChange` from command output.
- [x] Execution file-change card requires semantic payload (`toolType=fileChange` or semantic fileChange diff markers).
- [x] Pure commandExecution items stay command cards even when incidental file paths exist.
- [x] Legacy fallback remains only for older data shape and no synthetic `+0/-0` injection for new-turn canonical flow.

## Backend/projector cleanup

- [x] Canonical-first merge for `changesAppend/changesReplace` hardened in projector logic.
- [x] Explicit canonical-empty arrays are authoritative (no fallback hydration from mirror fields).
- [x] Mirror compatibility (`outputFiles`/`files*`) still synchronized from canonical output.
- [x] Migration-only fallback branches not needed for new-turn canonical path were removed/trimmed.

## Contract and compatibility

- [x] No new API endpoint introduced.
- [x] No new runtime flag introduced.
- [x] Wire fields retained for compatibility window (`outputFiles`, `files*`).

## Test hardening

- [x] Frontend tests updated to remove command-text inference assumptions.
- [x] Backend tests added for canonical-empty authority in v2/v3 projector and audit hydration.
- [x] Integration parity gate remains green for execution/audit lifecycle coverage.
