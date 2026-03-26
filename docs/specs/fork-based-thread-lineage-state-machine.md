# Fork-Based Thread Lineage State Machine

Status: draft spec for review. Proposed fork-based replacement for the current seed-heavy thread model in `thread-state-model.md` and the review-thread parts of `review-node-checkpoint.md`.

## Purpose

This document defines a fork-first thread lineage model built on the Codex app server `thread/fork` API.

The goal is to make thread inheritance match task inheritance:

- `root.audit` is the canonical trunk for the root task
- every downstream task thread is created by forking an upstream canonical thread
- fork inherits upstream conversation context that existed before the fork point
- canonical artifacts (frame, spec, split package, checkpoints) are persisted to local storage and injected into prompts at workflow boundaries by prompt builders

## Scope

This spec covers:

- thread creation and lineage
- persist-before-boundary rules
- canonical artifact storage
- task node thread state machine
- review node checkpoint thread state machine
- execution, split, local review, and rollup flow
- rebuild and recovery rules when a Codex thread is lost

This spec does not lock down:

- frontend layout details
- exact prompt wording
- exact SSE payload shapes
- post-v1 multi-split support

## Core Decisions

1. `root.audit` is the only task thread created with `thread/start`.
2. Every other thread in the lineage is created with `thread/fork`.
3. Fork is a one-time snapshot, not a live sync. It carries upstream conversation context only.
4. Any canonical artifact required by a downstream workflow must be persisted to local storage before that workflow boundary is crossed.
5. `ask_planning` is forked from the node's own `audit`.
6. `execution` is forked from the node's own `audit`.
7. A review node owns one canonical `audit` thread in v1. It is forked from the parent node's `audit` after split is persisted.
8. Sequential sibling tasks are forked from the review node's `audit` thread.
9. Canonical artifacts are never appended directly to Codex threads as synthetic records. They are persisted to local storage and injected into prompts at workflow boundaries by prompt builders. The Codex app server API does not support silent message insertion; the only way to add content is `run_turn_streaming()`, which runs a full AI turn. Rather than waste AI turns on synthetic inserts, the system keeps Codex threads for real conversations and uses local storage plus prompt injection for canonical data delivery.
10. In v1, a node may split at most once and split happens before any review-thread fork for that split.
11. In v1, split runs on the parent node's `audit` thread directly.
12. Local storage is the sole source of truth for canonical artifacts. The Codex app server holds conversation history only. Recovery rebuilds from local storage; there is no need to replay canonical records into Codex threads.
13. In v1, split retries remain on `parent.audit` and are capped at one retry after the initial attempt.
14. In v1, `ask_planning` is created lazily on first ask interaction, not eagerly when a node reaches its turn.
15. In v1, each new child's first prompt includes child assignment context injected from storage by the prompt builder.
16. In v1, final rollup analysis remains in `review.audit`; there is no dedicated `review.integration` thread.

## Terminology

| Term | Meaning |
|------|---------|
| Canonical thread | A thread used as a stable upstream source for future forks |
| Disposable thread | A thread that can be recreated from a canonical ancestor without losing official state |
| Persist-before-boundary | The rule that all canonical artifacts required by a downstream workflow must be persisted to local storage before the workflow boundary is crossed |
| Workflow boundary | A point where the system transitions between phases and prompt builders inject canonical data from storage into the next turn or fork |
| Prompt injection | Loading canonical artifacts from local storage and including them in the prompt sent to a Codex thread at a workflow boundary |
| Review thread | The review node's canonical `audit` thread, forked from the parent audit after split |
| Checkpoint | An accepted child result represented by child summary plus child SHA, persisted to `review_state.json` |
| Rollup | The final aggregated review result computed from the review thread after all child checkpoints are present |

## Thread Topology

### Task nodes

Task nodes use three thread roles:

| Role | Purpose | Creation source |
|------|---------|-----------------|
| `audit` | Canonical node record, split source, execution source, local review thread | Root: `start_thread`; child: `fork(review.audit)` |
| `ask_planning` | Working shaping thread for frame, clarify, spec | `fork(task.audit)` |
| `execution` | Automated implementation thread | `fork(task.audit)` |

### Review nodes

Review nodes use one thread role in v1:

| Role | Purpose | Creation source |
|------|---------|-----------------|
| `audit` | Canonical checkpoint and rollup thread | `fork(parent.audit)` after split is persisted |

`integration` is not part of the v1 target model. Final rollup analysis runs in the review node's `audit` thread after all child checkpoints are present.

## Session Metadata

Each persisted chat session keeps normal message history plus lineage metadata:

```json
{
  "thread_id": "codex-thread-id",
  "thread_role": "audit",
  "forked_from_thread_id": "upstream-thread-id-or-null",
  "forked_from_node_id": "upstream-node-id-or-null",
  "forked_from_role": "audit-or-null",
  "fork_reason": "root_bootstrap | ask_bootstrap | execution_bootstrap | review_bootstrap | child_activation",
  "lineage_root_thread_id": "root-audit-thread-id",
  "active_turn_id": null,
  "messages": [],
  "created_at": "ISO",
  "updated_at": "ISO"
}
```

Local session annotations (system messages written to the `messages` array for UI display, such as "Frame confirmed" or "Spec confirmed") are separate from the Codex thread state. They appear in the chat view but do not participate in fork inheritance and are not delivered to the Codex app server.

## Canonical Artifact Storage

Canonical artifacts are the structured outputs of each workflow phase. They are persisted to local storage and injected into prompts at workflow boundaries. They are never written directly to Codex threads.

### Artifact locations

| Artifact | Storage location | Produced by | Consumed at boundary |
|----------|-----------------|-------------|---------------------|
| Project root context | tree state snapshot | project bootstrap | root audit `start_thread` base instructions |
| Confirmed frame | `frame.md` + frame metadata in node folder | ask_planning confirm | split prompt, execution prompt |
| Confirmed spec | `spec.md` + spec metadata in node folder | ask_planning confirm | execution prompt |
| Split package | tree state + review state | split acceptance | review fork prompt, child activation prompt |
| Child assignment | review state pending siblings manifest | split acceptance / sibling activation | child first turn prompt |
| Checkpoint (summary + SHA) | `review_state.json` per review node | local review acceptance | next sibling activation prompt, rollup prompt |
| Rollup result | `review_state.json` per review node | rollup completion | open package review — prompt builder injects into first package review turn on parent audit |
| Execution result | `execution_state.json` per node | execution completion | open local review — prompt builder injects into first review turn on audit |

### Rules

1. Canonical artifacts are written to local storage by backend services, not by free-form user chat.
2. Canonical artifacts are immutable once persisted except for status field updates.
3. Child local review chat happens in `child.audit`, but only the accepted summary plus SHA is persisted to `review_state.json` for upstream consumption.
4. Parent receives the final rollup result from `review_state.json`, not intermediate child checkpoints.
5. No workflow boundary may be crossed until its required artifacts are persisted to local storage.
6. UI annotations in the local session `messages` array are cosmetic only and do not affect fork lineage or prompt injection.
7. Clarified answers produced during `ask_planning` are working material, not standalone canonical artifacts. Any clarified outcome that must survive recovery or be consumed by a downstream workflow must be captured in the confirmed frame or the confirmed spec. If a clarified answer is not reflected in frame or spec, it is ephemeral and will not be available after `ask_planning` is re-forked.

## Global Fork Rules

### Rule 1: Root bootstrap

When a project is created or attached:

1. Create `root.audit` with `thread/start`, passing project context as base instructions

### Rule 2: Ask bootstrap

When a task node first needs shaping chat:

1. Ensure the node's `audit` thread exists
2. Fork `ask_planning` from that `audit` thread
3. Continue all frame, clarify, and spec discussion in `ask_planning`

### Rule 3: Confirm frame

When frame is confirmed in `ask_planning`:

1. Persist the frame file and frame metadata to the node folder
2. Optionally write a local session annotation to `audit` messages for UI display
3. Do not cross any downstream workflow boundary until persistence completes

### Rule 4: Confirm spec

When spec is confirmed in `ask_planning`:

1. Persist the spec file and spec metadata to the node folder
2. Optionally write a local session annotation to `audit` messages for UI display
3. Do not cross the execution boundary until persistence completes

### Rule 5: Finish Task

When the user clicks Finish Task:

1. Validate that spec is persisted in the node folder
2. Fork `execution` from `audit`
3. Run the execution turn with frame and spec content loaded from storage and injected into the execution prompt by the prompt builder

### Rule 6: Split

In v1, split happens on the node's `audit` thread directly.

When split is initiated:

1. Load confirmed frame from storage and inject into the split prompt
2. Run the split turn on `parent.audit`
3. If split validation fails, retry at most one additional time on the same `parent.audit` thread

When split is accepted:

4. Persist the split structure to tree state and review state
5. Fork `review.audit` from `parent.audit`
6. Materialize the first child
7. Fork `child1.audit` from `review.audit`

Because split runs on `parent.audit` directly in v1, split prompts must be structured and retry behavior is capped at one retry to avoid contaminating downstream lineage with noisy failed attempts.

### Rule 7: Child activation

When a later sibling becomes active:

1. Ensure the latest accepted checkpoint is persisted in `review_state.json`
2. Materialize the next child node in tree state
3. Fork that child's `audit` thread from `review.audit`
4. When shaping begins, fork that child's `ask_planning` thread from the child's `audit`
5. The child's first prompt includes child assignment and prior sibling checkpoint summaries, loaded from storage by the prompt builder

### Rule 8: Local review acceptance

When a child task's local review is accepted:

1. Persist the accepted summary and head SHA to `review_state.json`
2. Only after persistence completes may the next sibling be activated and forked from `review.audit`

### Rule 9: Final rollup

When all materialized children have accepted local review:

1. Mark rollup as ready in review state
2. Load all checkpoint summaries from `review_state.json` and inject into the rollup prompt
3. Run final rollup analysis inside `review.audit`
4. Persist the rollup result to `review_state.json`

### Rule 10: Open local review

When execution completes and the node transitions to `local_review_open`:

1. Execution result is already persisted in `execution_state.json`
2. When the user sends their first review message in `audit`, the prompt builder loads and injects:
   - confirmed frame from node folder
   - confirmed spec from node folder
   - execution result (head SHA, completion status) from `execution_state.json`
3. The audit thread already has conversation context from shaping and earlier interactions via its history

### Rule 11: Open package review

When the rollup result is ready and the parent node transitions to `package_review_open`:

1. Rollup result is already persisted in `review_state.json`
2. When the user sends their first package review message in the parent `audit`, the prompt builder loads and injects:
   - confirmed frame from parent node folder
   - split package from tree/review state
   - rollup result (aggregated summary, child outcomes) from `review_state.json`
3. The parent audit thread already has conversation context from shaping and split interactions via its history

## Task Node State Machine

The task node thread model is event-driven and derived from persisted state plus session existence.

### States

| State | Meaning |
|------|---------|
| `audit_ready` | Node canonical audit exists and is the fork source for all downstream task threads |
| `shaping_open` | `ask_planning` exists and shaping may continue |
| `frame_confirmed` | Confirmed frame is persisted to node folder |
| `spec_confirmed` | Confirmed spec is persisted to node folder |
| `execution_running` | `execution` was forked from `audit` and execution is active |
| `local_review_open` | Execution completed and `audit` is open for local review |
| `local_review_accepted` | Accepted summary plus SHA has been persisted to review state |
| `split_applied` | Split structure is persisted and review thread has been created |
| `package_review_open` | Rollup result is available in review state and parent audit is open for package review |
| `terminal` | Root package review or root local review is complete and the project-level task is done |

### Task node transitions

| Event | Preconditions | Actions | Next state |
|------|---------------|---------|-----------|
| Root bootstrap | root node exists | `start(root.audit)` with project context in base instructions | `audit_ready` |
| Child activation | review thread exists and child is selected | `fork(child.audit <- review.audit)` | `audit_ready` |
| Open ask | task audit exists and no ask thread yet | `fork(ask <- audit)` | `shaping_open` |
| Confirm frame | shaping thread active | persist frame to node folder | `frame_confirmed` |
| Confirm spec | frame already confirmed | persist spec to node folder | `spec_confirmed` |
| Finish Task | `spec_confirmed`; node is leaf | `fork(execution <- audit)` and run with frame/spec injected from storage | `execution_running` |
| Execution completed | execution active | persist `head_sha` to execution state; prompt builder will inject execution context at next turn (Rule 10) | `local_review_open` |
| Accept local review (non-root) | `local_review_open`; node is not root | persist checkpoint to review state | `local_review_accepted` |
| Accept local review (root) | `local_review_open`; node is root | mark project complete | `terminal` |
| Split accepted | frame confirmed; node not executing; node has not split before | persist split to tree/review state; `fork(review.audit <- parent.audit)`; `fork(child1.audit <- review.audit)` | `split_applied` |
| Parent receives final rollup | review rollup completed | rollup result available in review state; prompt builder will inject rollup context at next turn (Rule 11) | `package_review_open` |
| Package review chat | `package_review_open` | user and agent review the final package in parent audit | `package_review_open` |
| Mark done (non-root) | `package_review_open`; node is not root | persist checkpoint to parent review state | `local_review_accepted` |
| Mark done (root) | `package_review_open`; node is root | mark project complete | `terminal` |

## Review Node State Machine

Review nodes have a single canonical `audit` thread in v1.

### States

| State | Meaning |
|------|---------|
| `forked_from_parent` | Review audit was forked from parent audit after split is persisted |
| `checkpointing` | Review state is receiving accepted child checkpoints |
| `ready_for_rollup` | All child checkpoints are persisted and no further sibling fork will occur |
| `rollup_completed` | Rollup result is persisted to review state |

### Review node transitions

| Event | Preconditions | Actions | Next state |
|------|---------------|---------|-----------|
| Review bootstrap | split persisted to tree/review state | `fork(review.audit <- parent.audit)` | `forked_from_parent` |
| Accept child review | child local review accepted | persist checkpoint to review state | `checkpointing` |
| Activate next sibling | checkpoint persisted | fork next child audit from review audit | `checkpointing` |
| All children accepted | no pending siblings and all child reviews accepted | mark review ready for rollup | `ready_for_rollup` |
| Rollup complete | review ready for rollup | run rollup in review audit with checkpoints injected from storage; persist rollup to review state | `rollup_completed` |

## End-to-End Workflows

### Workflow A: Root task executes directly

1. `root.audit = start_thread()` with project context in base instructions
2. `root.ask = fork(root.audit)`
3. shape frame and spec in `root.ask`
4. persist frame and spec to node folder
5. `root.execution = fork(root.audit)` with frame/spec injected from storage into execution prompt
6. execute
7. persist execution result to execution state
8. local review opens in `root.audit`; prompt builder injects frame, spec, and execution result from storage into first review turn (Rule 10)
9. root accepts local review; move to `terminal`

### Workflow B: Root task splits into sequential children

1. `root.audit = start_thread()` with project context in base instructions
2. `root.ask = fork(root.audit)`
3. confirm frame in `root.ask`; persist frame to node folder
4. run split on `root.audit` with frame injected from storage into split prompt
5. persist split structure to tree/review state
6. `review.audit = fork(root.audit)`
7. `child1.audit = fork(review.audit)`
8. `child1.ask = fork(child1.audit)`; child assignment injected from storage into first prompt
9. child1 shapes spec; persist spec to child1 node folder
10. child1 execution with frame/spec injected from storage
11. child1 local review; persist `K1(summary, sha)` to `review_state.json`
12. `child2.audit = fork(review.audit)`; child assignment + K1 summary injected from storage into first prompt
13. repeat until final child is accepted
14. run final rollup in `review.audit` with all checkpoints injected from storage into rollup prompt
15. persist rollup result to `review_state.json`
16. root reviews rollup package in `root.audit`; prompt builder injects frame, split package, and rollup result from storage into first package review turn (Rule 11)
17. root accepts; move to `terminal`

## Recovery and Rebuild Rules

Fork lineage depends on Codex server thread persistence. Local storage is always the canonical source for artifacts, so recovery never needs to replay canonical records into threads.

### Recovery principle

If a thread is lost on the Codex app server, re-fork from the nearest surviving canonical ancestor. Prompt builders inject whatever artifacts the re-forked thread needs from local storage at the next turn.

### Rebuild policy by thread type

| Lost thread | Rebuild rule |
|------------|--------------|
| `root.audit` | `start_thread()` a new root audit with project context in base instructions |
| `task.ask_planning` | Re-fork from the current task audit; ask is disposable |
| `task.execution` before completion | Mark execution interrupted; allow explicit retry by re-forking from current task audit |
| `child.audit` | Fork from current `review.audit`; prompt builder injects child assignment from storage at next turn |
| `review.audit` | Fork from current `parent.audit`; prompt builder injects checkpoint context from `review_state.json` at next turn |

### Replay sources

Recovery relies on persisted local state:

- `frame.md` and frame metadata
- `spec.md` and spec metadata
- `review_state.json` (checkpoints, rollup, pending siblings)
- `execution_state.json`
- tree state and split payload records

Session message history is preserved for UI continuity but is not required for lineage recovery.

## Invariants

1. Every non-root thread has exactly one `forked_from_thread_id`.
2. Every workflow boundary crossing is ordered after all required artifacts are persisted to local storage.
3. `ask_planning` is never the fork source for `execution`.
4. `review.audit` is always forked from `parent.audit`, never from `parent.ask_planning`.
5. Sequential siblings always fork from the same `review.audit`.
6. Parent receives the final rollup result, not each child checkpoint.
7. In v1, review nodes do not own `ask_planning` or `execution`.
8. In v1, split is single-use per node and happens before review fork for that split.
9. Any context needed for deterministic rebuild must exist in persisted local storage, not solely on the Codex app server.
10. Fork operations and artifact persistence that gate downstream forks are serialized under one project-scoped critical section; no two lineage-mutating operations may race on the same canonical source thread.

## Current Implementation Gaps

This target spec differs from the current codebase in several major ways:

- current services create most threads with `start_thread()` or recover with `resume_thread()`
- current model seeds context into sessions instead of using fork inheritance plus prompt injection from storage
- current review node model uses an `integration` thread instead of a single canonical `audit` review thread
- current split flow uses a project-level split thread rather than the parent node's `audit`

The migration path should therefore update:

- thread role validation rules
- session metadata schema
- chat, finish task, split, and review services to use `fork_thread()`
- prompt builders to load canonical artifacts from storage at workflow boundaries
- rebuild logic for missing app-server threads
- tests that currently assert seed-based thread creation

## Resolved V1 Decisions

1. `ask_planning` is created lazily on first ask interaction.
2. Each new child's first prompt includes child assignment context injected from storage by the prompt builder.
3. Split retries remain on `parent.audit` in v1 and are capped at one retry after the initial attempt.
4. Final rollup analysis remains in `review.audit` in v1.

## Deferred V2 Considerations

1. A forked split worker may be introduced later to keep `parent.audit` cleaner during split retries.
2. A dedicated `review.integration` thread may be introduced later if rollup analysis in `review.audit` proves too noisy or too difficult to recover cleanly.
