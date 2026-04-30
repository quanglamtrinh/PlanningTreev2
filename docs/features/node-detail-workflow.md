# Node Detail Workflow

## Scope

The node detail card provides a sequential workflow for shaping tasks through three artifacts: Frame, Clarify, and Spec. Each artifact must be confirmed before the next becomes available.

- Frame: markdown document â€” human-friendly thin spec (steering source of truth). Codex writes it, user reviews and edits the markdown.
- Clarify: choice-based Q&A â€” AI generates concrete options per question for unresolved steering items. User selects an option or types a custom answer. The only structured UI in this workflow.
- Spec: markdown document â€” agent-friendly expanded version initialized from frame + clarify. Codex writes it, user reviews and edits the markdown.

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

Active:
- `GET /v4/projects/{project_id}/nodes/{node_id}/documents/{kind}` - read frame.md or spec.md
- `PUT /v4/projects/{project_id}/nodes/{node_id}/documents/{kind}` - write frame.md or spec.md
- `GET /v4/projects/{project_id}/nodes/{node_id}/detail-state` - derived tab unlock/stale state
- `POST /v4/projects/{project_id}/nodes/{node_id}/artifacts/frame/generate`
- `POST /v4/projects/{project_id}/nodes/{node_id}/artifacts/frame/confirm`
- `GET /v4/projects/{project_id}/nodes/{node_id}/clarify` - read clarify state
- `PUT /v4/projects/{project_id}/nodes/{node_id}/clarify` - update clarify answers
- `POST /v4/projects/{project_id}/nodes/{node_id}/artifacts/clarify/generate`
- `POST /v4/projects/{project_id}/nodes/{node_id}/artifacts/clarify/confirm`
- `POST /v4/projects/{project_id}/nodes/{node_id}/artifacts/spec/generate`
- `POST /v4/projects/{project_id}/nodes/{node_id}/artifacts/spec/confirm`

## Storage Files (per node directory)

| File | Format | Content | Purpose |
|------|--------|---------|---------|
| `frame.md` | Markdown | Frame artifact content | Canonical human-readable document |
| `frame.meta.json` | JSON | `{ revision, confirmed_revision, confirmed_at }` | Workflow metadata only â€” no content |
| `clarify.json` | JSON | Choice-based Q&A: questions with AI-generated options, selected option / custom answer + metadata | Structured Q&A state |
| `spec.md` | Markdown | Spec artifact content | Canonical human-readable document |
| `spec.meta.json` | JSON | `{ source_frame_revision, source_clarify_revision, confirmed_at }` | Workflow metadata only â€” no content |

## Service Layer

- `node_document_service.py` â€” thin raw I/O (read/write text and JSON files). No business logic.
- `node_detail_service.py` â€” business rules: confirm transitions, title sync, clarify seeding, spec initialization, stale detection, detail state derivation.

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
| Clarify | All questions have `selected_option_id != null` OR `custom_answer.trim() != ""`. Zero questions = auto-confirm. |
| Spec | `spec.md` is non-empty. Confirm is a "reviewed" marker. |

