# Node Detail Workflow

## Scope

The node detail card provides a sequential workflow for shaping tasks through three artifacts: Frame, Clarify, and Spec. Each artifact must be confirmed before the next becomes available.

- Frame: markdown document — human-friendly thin spec (steering source of truth). Codex writes it, user reviews and edits the markdown.
- Clarify: structured Q&A — task-shaping field questions for unresolved steering items. The only structured UI in this workflow.
- Spec: markdown document — agent-friendly expanded version initialized from frame + clarify. Codex writes it, user reviews and edits the markdown.

The Describe tab remains unchanged (read-only node metadata).

**Architecture: markdown-first, agent-mediated.** Frame and Spec are markdown files on disk. The UI shows a markdown editor with confirm/status controls. No backend parse/serialize cycle for form rendering. Only Clarify uses structured data (JSON) because it's a Q&A workflow.

## Tab Progression

| Tab | State source | UI | Unlock condition |
|-----|-------------|-----|-----------------|
| Describe | Always | Read-only metadata | Always available |
| Frame | `frame.md` + `frame.meta.json` | Markdown editor + confirm | Always available |
| Clarify | `clarify.json` | Structured Q&A panel | Frame confirmed |
| Spec | `spec.md` + `spec.meta.json` | Markdown editor + confirm | Clarify confirmed |

Downstream tabs become **stale** (not wiped) when upstream artifacts change after confirmation. User can acknowledge stale and continue, or re-initialize.

## Public Routes

Existing (unchanged):
- `GET /v1/projects/{project_id}/nodes/{node_id}/documents/{kind}` — read frame.md or spec.md
- `PUT /v1/projects/{project_id}/nodes/{node_id}/documents/{kind}` — write frame.md or spec.md

New:
- `GET /v1/projects/{project_id}/nodes/{node_id}/detail-state` — derived tab unlock/stale state
- `POST /v1/projects/{project_id}/nodes/{node_id}/confirm-frame` — confirm frame, seed clarify
- `GET /v1/projects/{project_id}/nodes/{node_id}/clarify` — read clarify state
- `PUT /v1/projects/{project_id}/nodes/{node_id}/clarify` — update clarify answers
- `POST /v1/projects/{project_id}/nodes/{node_id}/confirm-clarify` — confirm clarify, initialize spec
- `POST /v1/projects/{project_id}/nodes/{node_id}/confirm-spec` — confirm spec

Future (AI phases):
- `POST .../generate-frame`
- `POST .../generate-clarify`
- `POST .../generate-spec`

## Storage Files (per node directory)

| File | Format | Content | Purpose |
|------|--------|---------|---------|
| `frame.md` | Markdown | Frame artifact content | Canonical human-readable document |
| `frame.meta.json` | JSON | `{ revision, confirmed_revision, confirmed_at }` | Workflow metadata only — no content |
| `clarify.json` | JSON | Questions, answers, resolution status + metadata | Structured Q&A state |
| `spec.md` | Markdown | Spec artifact content | Canonical human-readable document |
| `spec.meta.json` | JSON | `{ source_frame_revision, source_clarify_revision, confirmed_at }` | Workflow metadata only — no content |

## Service Layer

- `node_document_service.py` — thin raw I/O (read/write text and JSON files). No business logic.
- `node_detail_service.py` — business rules: confirm transitions, title sync, clarify seeding, spec initialization, stale detection, detail state derivation.

## Title Sync

Confirming frame extracts the `# Task Title` section content from frame.md and pushes it to `node.title` in the tree snapshot. Frame is the source of truth for title once confirmed.

## Three Actions

| Action | Trigger | Effect |
|--------|---------|--------|
| Save (draft) | Autosave 800ms debounce | Persists markdown content. Bumps `revision`. No state transition. |
| Confirm | User clicks Confirm | Sets `confirmed_at`, `confirmed_revision = revision`. Unlocks next tab. |
| Generate | User clicks Generate (AI phases) | Async AI writes content. Does NOT auto-confirm. User reviews first. |

## Confirm Readiness Rules

| Artifact | Can confirm when |
|----------|-----------------|
| Frame | `frame.md` is non-empty (has content beyond whitespace) |
| Clarify | All questions have `resolution_status != "open"` (each answered, assumed, or deferred). Zero questions = auto-confirm. |
| Spec | `spec.md` is non-empty. Confirm is a "reviewed" marker. |
