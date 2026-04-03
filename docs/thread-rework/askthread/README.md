# Ask Thread Rework

Primary planning docs for migrating ask thread from legacy V1 to V3:

- `docs/thread-rework/askthread/ask-thread-v3-phased-roadmap.md`

This directory is reserved for:

- ask-lane architecture and rollout plans
- phase-level execution skeletons
- implementation gate and risk checklists for ask migration

Locked scope baseline (already decided):

- Ask is a dedicated lane in V3.
- Ask uses shared V3 by-id route namespace and thread registry.
- Ask UX is rendered by metadata shell (not coupled to ask transcript rendering).
- Metadata shell must persist through ask reset.
- Ask lane remains available after Finish Task, but in strict read-only mode.
- Frame/Clarify/Spec generation is allowed, but file writes are backend-owned and restricted to workflow artifacts.
