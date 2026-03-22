# Artifact Semantics — Node Detail Workflow

Defines the data model, state machine, and rules for the three node detail artifacts: Frame, Clarify, and Spec.

**Architecture: markdown-first, agent-mediated.** Frame and Spec are markdown files. Codex reads and writes them directly. The UI shows a markdown editor. No backend parse/serialize cycle to structured fields. Only Clarify uses structured JSON because it's a Q&A workflow, not a document.

## 1. Title Ownership

`# Task Title` section in frame.md is the source of truth for the node's title.

- When frame is confirmed, `node_detail_service` extracts the first line of the `# Task Title` section from frame.md and pushes it to `node.title` in `tree.json`.
- Before a frame exists, `node.title` set via inline tree edit is the initial seed.
- The Describe tab shows `node.title` from the tree (which stays in sync after frame confirm).

## 2. Three Actions

| Action | Trigger | Effect |
|--------|---------|--------|
| **Save (draft)** | Autosave (800ms debounce) | Persists markdown content to disk. Bumps `revision` in sidecar. No state transition. |
| **Confirm** | Explicit user click | Sets `confirmed_at`, sets `confirmed_revision = revision`. Unlocks next tab. May trigger downstream seeding/init. |
| **Generate** | Explicit user click (AI phases) | Async AI job writes content to disk. Does NOT auto-confirm. User must review then confirm. |

## 3. State Machine

### Tab states

Each tab has one of three states, derived from sidecar metadata:

| State | Meaning | UX |
|-------|---------|-----|
| **Locked** | Upstream artifact not yet confirmed | Tab not clickable, shows lock icon |
| **Active** | Unlocked and current with upstream | Normal editable state |
| **Stale** | Unlocked but upstream changed since last confirmation | Shows "needs review" banner. Content preserved, not wiped. |

### Unlock rules

| Tab | Unlock condition |
|-----|-----------------|
| Describe | Always available |
| Frame | Always available |
| Clarify | `frame.meta.json` has `confirmed_revision` ≥ 1 |
| Spec | `clarify.json` has `confirmed_at` set |

### Stale rules

| Tab | Stale condition |
|-----|----------------|
| Clarify | `clarify.source_frame_revision` < `frame.confirmed_revision` |
| Spec | `spec.source_frame_revision` < `frame.confirmed_revision` OR `spec.source_clarify_revision` mismatch |

### Stale resolution

When a tab is stale, the user can:
- **Acknowledge and continue** — dismiss the banner, keep editing
- **Re-initialize from upstream** — re-seed clarify or re-init spec (with merge where possible, warning before overwrite)

Re-editing frame after confirmation does NOT lock clarify or spec. It only marks them stale when frame's `confirmed_revision` advances on next confirm.

## 4. Confirm Readiness Rules

| Artifact | Can confirm when | Notes |
|----------|-----------------|-------|
| Frame | `frame.md` is non-empty (content beyond whitespace) | No structural validation — markdown is freeform |
| Clarify | All questions have `selected_option_id != null` OR `custom_answer.trim() != ""` | Zero questions = auto-confirm, immediately unlock spec |
| Spec | `spec.md` is non-empty | Confirm is a "reviewed" marker, no structural gate |

## 5. Revision Tracking

No separate `workflow_state.json`. Each artifact carries its own metadata. Sidecar files hold **workflow metadata only** — no parsed fields cache. The one exception is `confirmed_content` in frame.meta.json, which snapshots frame.md at confirm time for downstream provenance (clarify generation must use confirmed content, not the live draft).

### frame.meta.json
```json
{
  "revision": 0,
  "confirmed_revision": 0,
  "confirmed_at": null,
  "confirmed_content": ""
}
```
- `revision` increments on every save (draft or confirmed).
- `confirmed_revision` is set to current `revision` value when user confirms.
- `confirmed_at` is ISO timestamp of last confirm action.
- `confirmed_content` is the full frame.md text snapshotted at confirm time. Used by clarify generation to ensure provenance matches `confirmed_revision` even if frame.md has post-confirm draft edits.

### clarify.json (metadata fields alongside content)
```json
{
  "schema_version": 2,
  "source_frame_revision": 0,
  "confirmed_revision": 0,
  "confirmed_at": null,
  "questions": [...],
  "updated_at": ""
}
```
- `schema_version` tracks the clarify data model version. Current: 2 (choice-based).
- `source_frame_revision` is `frame.confirmed_revision` at time clarify was seeded.
- `confirmed_revision` is the clarify revision at time of confirm. Used by spec init (`source_clarify_revision`).
- `confirmed_at` is ISO timestamp of last confirm action.

### spec.meta.json
```json
{
  "source_frame_revision": 0,
  "source_clarify_revision": 0,
  "confirmed_at": null
}
```
- `source_frame_revision` is `frame.confirmed_revision` at time spec was initialized.
- `source_clarify_revision` is the effective clarify revision at time of spec init.
- `confirmed_at` is ISO timestamp of last confirm action.

## 6. Frame — Markdown Artifact

Frame is a markdown file (`frame.md`) with conventional sections. Codex writes it following this structure; the user can edit freely.

### Conventional sections
```markdown
# Task Title
Study Planner MVP

# User Story / Problem
Sinh viên cần một công cụ đơn giản...

# Functional Requirements
- tạo môn học
- tạo deadline bài tập

# Success Criteria
- có thể dùng để quản lý tuần học đầu tiên

# Out of Scope
- không có collaboration

# Task-Shaping Fields
- target platform: mobile web
- reminder channel:
- user scope:
- storage level:
```

### Rules
- Frame.md is the canonical artifact. No structured representation is maintained alongside it.
- Backend does NOT parse frame.md into structured fields for API responses. The API returns raw markdown content (same as today).
- The only backend parsing is on **confirm**: extract `# Task Title` for title sync and `# Task-Shaping Fields` for clarify seeding.
- User edits markdown directly in the editor. Agent writes markdown directly via generation.

## 7. Clarify — Structured Q&A

Clarify is the only structured artifact in this workflow. It uses JSON because it's a Q&A interaction, not a document.

### Question schema (choice-based)
| Field | Type | Description |
|-------|------|-------------|
| field_name | string | Name of the shaping field from frame |
| question | string | Clarification question for the user |
| why_it_matters | string | Why this field affects steering |
| current_value | string | Value from frame (may be empty) |
| options | ClarifyOption[] | AI-generated concrete options |
| selected_option_id | string \| null | ID of user-selected option, or null if unresolved |
| custom_answer | string | User's freeform answer (alternative to option selection) |
| allow_custom | boolean | Whether custom freeform answer is allowed (always true) |

**Resolution rule:** A question is resolved when `selected_option_id != null` OR `custom_answer.trim() != ""`. Both null/empty = unresolved (open).

**Mutual exclusivity:** Selecting an option clears `custom_answer`; typing a custom answer clears `selected_option_id`. Both enforced on frontend and backend.

### ClarifyOption schema
| Field | Type | Description |
|-------|------|-------------|
| id | string | Stable identifier — `snake_case(value)`, enforced by backend |
| label | string | Short display label for the option |
| value | string | Concrete value this option represents |
| rationale | string | Why this option makes sense |
| recommended | boolean | Exactly one option per question must be `true` |

### Seeding rule (only unresolved steering fields)
When frame is confirmed, `node_detail_service` reads `# Task-Shaping Fields` from frame.md:
- Fields with a non-empty value (e.g., `- target platform: mobile web`) → **skip**, already resolved
- Fields with no value or empty value (e.g., `- storage level:`) → create a clarify question

This matches details.md principle: only unknowns with steering value at the current layer become questions. Resolved fields don't need re-asking.

### Re-seeding on stale
When re-seeding from updated frame:
- New unresolved fields → add new questions
- Removed fields → drop from questions list
- Matching field names → preserve `selected_option_id` (if option id still exists in new options) and always preserve `custom_answer`

## 8. Spec — Markdown Artifact

Spec is a markdown file (`spec.md`) with conventional sections. Initialized from frame + clarify, then freely editable.

### Conventional sections
```markdown
# Working Goal
Build a single-user study planner MVP...

# Source Frame
Frame revision 2

# Functional Requirements
- allow creating and editing subjects
...

# Success Criteria
...

# Out of Scope
...

# Assumptions & Defaults
- single-user unless stated otherwise

# Task-Shaping Fields
- target platform: mobile-responsive web
...

# Key Risks / Boundaries
- reminder feature may expand scope

# Clarification Notes
- target platform: selected "mobile-responsive web" (recommended option)
...
```

### Initialization (deterministic, writes markdown directly)
When clarify is confirmed, `node_detail_service.init_spec()`:
1. Reads frame.md sections and clarify.json questions/choices
2. Composes spec.md as markdown text:
   - `# Working Goal` = "{Task Title}: {User Story}" from frame
   - `# Source Frame` = "Frame revision {confirmed_revision}"
   - `# Functional Requirements`, `# Success Criteria`, `# Out of Scope` = copied from frame.md
   - `# Assumptions & Defaults` = reasonable defaults from frame context
   - `# Task-Shaping Fields` = merged frame values + selected option values or custom answers from clarify
   - `# Key Risks / Boundaries` = empty (user fills or AI generates later)
   - `# Clarification Notes` = summary of clarify choices (which option was selected, or custom answer text)
3. Writes spec.md to disk
4. Creates spec.meta.json with source revisions

### Rules
- After initialization, spec.md is fully editable markdown. User can add implementation details, refine sections, etc.
- Spec must not contradict frame's intent/steering. If steering needs to change, user edits frame first.
- Re-initialization on stale: overwrites spec.md (with warning). User should review stale state before re-init.

## 9. AI Generation Thread Model (Phase 4+)

For AI generation phases:
- **Context source:** Reads chat history from `chat_state_store.py` for the node's existing thread.
- **Execution:** Creates a **separate generation thread** for the AI call. Does not reuse or pollute the user-facing chat thread identity.
- **Pattern:** Follows `split_service.py` — background job, state tracking, stale-job recovery.
- **Output:** AI writes directly to `frame.md` / `clarify.json` / `spec.md`. No intermediate structured representation.
- **One generic service:** `ArtifactGenerationService` parameterized by kind (frame|clarify|spec), not 3 separate services.
