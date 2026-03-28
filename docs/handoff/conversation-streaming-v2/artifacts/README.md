# Artifacts Folder Guidance

Use this folder to store implementation evidence for the conversation streaming V2 rollout.

Recommended structure:

- `artifacts/phase-0/`
- `artifacts/phase-1/`
- `artifacts/phase-2/`
- `artifacts/phase-3/`
- `artifacts/phase-4/`
- `artifacts/phase-5/`
- `artifacts/phase-6/`
- `artifacts/phase-7/`
- `artifacts/phase-8/`

Recommended contents per phase:

- fixture manifests
- payload captures
- verification notes
- command outputs worth preserving
- screenshots for UI phases
- handoff notes for partial completion or blockers

Rules:

- do not treat this folder as source of truth for the contract; the active contract lives in `docs/specs/conversation-streaming-v2.md`
- use this folder for evidence, not for unreviewed design changes
- link artifact files from the matching phase markdown document and from `progress.yaml` notes when helpful
