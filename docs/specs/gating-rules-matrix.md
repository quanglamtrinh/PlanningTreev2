# Gating Rules Matrix

Status: spec (Phase 1 artifact). Maps every user action to its preconditions.

## Purpose

This document is the single source of truth for what actions are allowed when. Services must enforce these rules. UI must disable actions that would fail.

## Matrix

### Shaping Actions

| Action | Preconditions | Error if violated |
|--------|--------------|-------------------|
| **Save Frame** | `shaping_frozen == false` | `ShapingFrozen` |
| **Save Spec** | `shaping_frozen == false` | `ShapingFrozen` |
| **Confirm Frame** | `frame.md` non-empty AND `shaping_frozen == false` | `InvalidRequest` / `ShapingFrozen` |
| **Confirm Clarify** | All questions have `selected_option_id` or non-empty `custom_answer` AND `shaping_frozen == false` | `InvalidRequest` / `ShapingFrozen` |
| **Confirm Spec** | Frame confirmed (`frame.meta.confirmed_revision >= 1`) AND `spec.md` non-empty AND `shaping_frozen == false` | `InvalidRequest` / `ShapingFrozen` |
| **Generate Frame** | `shaping_frozen == false` | `ShapingFrozen` |
| **Generate Clarify** | Frame confirmed AND `shaping_frozen == false` | `InvalidRequest` / `ShapingFrozen` |
| **Generate Spec** | Frame confirmed AND clarify confirmed AND `shaping_frozen == false` | `InvalidRequest` / `ShapingFrozen` |

### Structural Actions

| Action | Preconditions | Error if violated |
|--------|--------------|-------------------|
| **Split** | Frame confirmed AND clarify resolved AND `child_ids` empty AND `shaping_frozen == false` | `SplitNotAllowed` / `ShapingFrozen` |
| **Create Child** (manual) | Node exists AND not superseded | `InvalidRequest` |

### Execution Actions

| Action | Preconditions | Error if violated |
|--------|--------------|-------------------|
| **Finish Task** | Spec confirmed (`spec.meta.confirmed_at` non-null) AND node is leaf (`child_ids` empty) AND node status `ready` or `in_progress` AND `execution_state` does not exist | `FinishTaskNotAllowed` |

### Thread Actions

| Action | Preconditions | Error if violated |
|--------|--------------|-------------------|
| **Send message to ask_planning** | `shaping_frozen == false` (no execution_state exists) | `ThreadReadOnly` |
| **Send message to execution** | Never (execution is automated, user cannot send messages) | `ThreadReadOnly` |
| **Send message to audit** | `execution_state.status == completed` or later | `ThreadReadOnly` |
| **Reset ask_planning** | `shaping_frozen == false` | `ThreadReadOnly` |
| **Reset execution** | Never | `ThreadReadOnly` |
| **Reset audit** | Never (audit seed messages are immutable) | `ThreadReadOnly` |

### Review Actions

| Action | Preconditions | Error if violated |
|--------|--------------|-------------------|
| **Start local review** (Layer 1) | `execution_state.status == completed` | `ReviewNotAllowed` |
| **Accept local review** (Layer 1) | `execution_state.status == review_pending` AND user has provided summary | `ReviewNotAllowed` |
| **Activate next sibling** | Previous sibling `execution_state.status == review_accepted` AND checkpoint K(N) exists AND next `pending_siblings` entry exists | `SiblingActivationNotAllowed` |
| **Start integration rollup** (Layer 2) | `rollup.status == ready` (auto-triggered when all siblings accepted) | `ReviewNotAllowed` |
| **Accept integration rollup** (Layer 2) | Integration agent has produced rollup summary AND user approves | `ReviewNotAllowed` |
| **Package audit** (Layer 3) | Rollup accepted AND package written to parent audit | N/A (happens in parent audit chat) |

## Derived UI State

The backend returns these derived booleans so the frontend doesn't need to re-derive gating logic:

| Field | Derivation | Used to gate |
|-------|-----------|-------------|
| `can_finish_task` | spec confirmed AND leaf AND status ready/in_progress AND no execution_state | Finish Task button |
| `shaping_frozen` | execution_state exists | All shaping tab interactions |
| `execution_started` | execution_state exists AND status != idle | Execution tab visibility |
| `execution_completed` | execution_state.status in {completed, review_pending, review_accepted} | Audit chat enablement |
| `can_accept_local_review` | execution_state.status == review_pending | Accept Review button |

## New Error Types

| Error | HTTP Status | When |
|-------|------------|------|
| `ShapingFrozen` | 409 Conflict | Attempting shaping action after Finish Task |
| `ThreadReadOnly` | 409 Conflict | Attempting to write to a read-only thread |
| `FinishTaskNotAllowed` | 400 Bad Request | Preconditions for Finish Task not met |
| `ReviewNotAllowed` | 400 Bad Request | Preconditions for review action not met |
| `SiblingActivationNotAllowed` | 400 Bad Request | Preconditions for sibling activation not met |

## Enforcement Layers

1. **Service layer** (primary): all precondition checks happen in service methods. This is the authoritative enforcement.
2. **Route layer**: routes pass through to services; no duplicate checks needed.
3. **Frontend** (secondary): UI uses derived state fields to disable buttons/actions. This is for UX only — the service layer is the real gate.

## Status Model Note

All execution/review gates use `execution_state.status`, NOT `node.status`. `node.status` remains coarse (`locked | draft | ready | in_progress | done`) and is NOT extended with execution/review values. See `execution-state-model.md` Status Model section.

## Invariant: shaping_frozen is permanent

Once `execution_state.json` exists, it is never removed. Therefore `shaping_frozen` is a permanent, irreversible state for a node. There is no "un-freeze" operation.
