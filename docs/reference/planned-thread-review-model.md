# Planned Thread and Review Model

Status: planned model reference. This document defines the intended model, not the current implementation.

## Purpose

This document captures the main conceptual model for:

- `audit`, `ask/planning`, and `execution` threads
- visible review nodes in the tree
- immutable confirmed frames
- confirmed-spec gating for execution
- local review in `audit`
- rollup review in review nodes
- upward handoff through accepted summary plus git SHA

The goal is to keep official task intent stable across split, execution, and review without mixing canonical task context with exploratory discussion.

## Scope

This document is intentionally about the main model only.

It does not lock down:

- storage schema
- route design
- UI edge cases
- git integration details
- low-level recovery behavior
- alternative split workflows beyond the current rule

Those can be specified later without changing the model described here.

## Core Decisions

The following decisions are considered part of the model:

1. A node can split at most once in the current model.
2. `ask/planning` owns discussion, clarification, and shaping before execution.
3. `audit` is the official record for a node while that node is still active in downstream workflow.
4. The confirmed `frame.md` of a node becomes immutable and read-only after confirmation.
5. `Finish Task` is allowed only when the node has `spec.md` and that spec has been confirmed.
6. `execution` is created only when the user clicks `Finish Task`.
7. When `Finish Task` starts execution, the node's shaping tabs become read-only.
8. `audit` is read-only for chat until execution finishes.
9. After execution finishes, `audit` becomes the place where user and agent perform local review for that node.
10. A visible review node remains part of the graph model.
11. Upward handoff currently consists of accepted summary plus SHA.
12. For sequential siblings such as `1.A -> 1.B -> 1.C`, sibling threads are created lazily when that sibling reaches its turn.

## Terms

| Term | Meaning |
|---|---|
| Node | The user-facing task in the tree. In the current model, it has one split path at most. |
| Audit thread | The canonical thread for official node context and post-execution local review. |
| Ask/planning thread | The discussion thread used to shape the task and confirm frame/spec. |
| Execution thread | The implementation thread created only after `Finish Task`. |
| Review node | A visible graph node dedicated to checkpointing subtree progress and final rollup review. |
| Checkpoint | The official subtree context maintained by the review node after accepted child review. |
| Local review | Review of one node's direct work, performed in that node's `audit` thread after execution. |
| Rollup review | Review of the integrated result of multiple children against the parent's intent. |
| Initial SHA | The baseline SHA for the current node turn. |
| Head SHA | The SHA after the node's execution work is completed. |
| Accepted summary | The official compact summary approved for handoff upward or forward. |

## High-Level Model

### 1. Node model

In the current model, a node represents one active task realization.

There is no alternate-version model here. A node can split only once. That matches the current product behavior and keeps the main model simple.

If richer alternative split flows are explored later, they should be specified in a later document rather than implicitly assumed here.

### 2. Thread roles

#### Audit

`audit` is the official record for a node.

Before execution completes, `audit` is not a free-form chat room. It is read-only from the user's point of view and should hold canonical task context such as:

- the node's split item
- the latest accepted summary plus SHA from the relevant checkpoint
- the node's confirmed frame
- the node's confirmed spec

After execution completes, `audit` opens for chat and becomes the place for local review. At that point the node is no longer a source of unresolved downstream shaping, so audit can tolerate review discussion and become noisier.

#### Ask/planning

`ask/planning` is the working discussion thread.

It is the place where the user and agent:

- discuss the task
- clarify assumptions
- draft and confirm the frame
- shape and confirm the spec

`ask/planning` is not created eagerly for every sibling. In the current model it is created lazily when that node reaches its turn.

#### Execution

`execution` does not exist by default.

It is created only when the user clicks `Finish Task`, and that is only allowed after the spec exists and has been confirmed.

`execution` should not reopen task intent. It implements a task that has already been shaped and frozen enough to execute.

### 3. Review node

The review node is a visible graph node.

Its purpose is:

- to maintain the official checkpoint of a subtree as sequential child tasks are accepted
- to provide the seed context for the next sequential sibling
- to perform final rollup review when the subtree is complete
- to hand accepted summary plus SHA upward to the parent

The review node is not the place for broad planning and not the place for implementation.

## Frame and Spec Semantics

### Confirmed frame

Before confirmation, `frame.md` may be drafted and discussed in `ask/planning`.

After confirmation:

- `frame.md` becomes immutable for that node
- `frame.md` becomes read-only
- the confirmed frame becomes part of the node's official audit context
- future split or review for that node must use the confirmed frame, not an editable draft

### Confirmed spec

`spec.md` is the execution gate.

Execution is not allowed until:

- `spec.md` exists
- `spec.md` has been confirmed

This keeps execution grounded in a reviewed task contract rather than only a high-level frame.

### Frozen shaping state after `Finish Task`

When the user clicks `Finish Task`:

- `execution` is created
- shaping stops for that node
- node detail shaping tabs become read-only

This creates a clear boundary between:

- task shaping
- task execution

## Split and Child Seeding

Split should be grounded in:

- the parent node's confirmed frame
- the repository/codebase context
- the accepted rationale for why the task is being decomposed

When split produces child work:

1. the parent retains its own `audit`
2. a visible review node is created for that child layer
3. child nodes are created
4. only the first sequential child is started immediately
5. later sequential children are started lazily, after earlier children complete review

This means later siblings do not begin from stale split-time context. They begin from the latest accepted checkpoint maintained by the review node.

## Local Review vs Rollup Review

### Local review

`local review` happens inside the node's `audit` thread after execution completes.

At that point:

- the user can chat in `audit`
- the agent can inspect the result of execution
- the node is reviewed against its own task contract

The core comparison is:

- `initial SHA`: the baseline SHA for this node's turn
- `head SHA`: the SHA produced after the node's execution work

The outcome of local review is an accepted summary plus the head SHA.

`local review` is about the node's own work only. It is not the full integration review of the entire parent layer.

### Rollup review

`rollup review` happens in the review node after the relevant children have completed local review.

It checks the integrated result of the subtree against:

- the parent frame
- the parent split rationale

It answers questions like:

- Do the children collectively satisfy the parent task?
- Does the realized subtree still match the reason the parent was split that way?
- Are there cross-child mismatches or integration gaps?

The outcome of rollup review is an accepted summary plus a SHA for upward handoff.

## Upward Handoff

The parent should not rely on raw child discussion history.

The parent should receive upward handoff in the form of:

- accepted summary
- SHA

This keeps upward context compact and official.

At the parent layer, the main question becomes:

"Does the accepted subtree result, represented by this summary and SHA, still match the parent's confirmed frame and split rationale?"

## Lazy Creation Rule for Sequential Siblings

For a sequential chain such as `1.A -> 1.B -> 1.C`, sibling threads are created lazily.

That means:

- `1.A audit` and `1.A ask/planning` are created when `1.A` starts
- `1.B audit` and `1.B ask/planning` do not exist yet
- after `1.A` finishes execution and local review is accepted, the review node emits a new checkpoint
- only then are `1.B audit` and `1.B ask/planning` created
- the same pattern repeats for `1.C`

This avoids stale sibling threads and keeps each sibling grounded in the latest accepted subtree context.

## Main Lifecycle

The main lifecycle of a node is:

1. The node receives official seed context.
2. `audit` and `ask/planning` are created when the node reaches its turn.
3. The team shapes the task in `ask/planning`.
4. `frame.md` is confirmed and becomes immutable.
5. `spec.md` is confirmed.
6. The user clicks `Finish Task`.
7. `execution` is created and shaping tabs become read-only.
8. Execution finishes and produces a head SHA.
9. `audit` opens for chat-based local review.
10. Local review compares initial SHA vs head SHA and produces accepted summary plus SHA.
11. The review node updates the subtree checkpoint.
12. If there is a next sequential sibling, that sibling's `audit` and `ask/planning` are created from the new checkpoint.
13. After the subtree is complete, the review node performs rollup review.
14. The review node hands accepted summary plus SHA upward to the parent.

## Worked Example

Consider a parent task split into:

```text
1.A -> 1.B -> 1.C
```

### Initial state

The parent has:

- a confirmed frame
- split rationale
- a visible review node for this layer

The review node holds the initial checkpoint `K0`.

`K0` contains the official context for starting the first child, including the baseline SHA for the subtree at this layer.

### 1.A

1. Create `1.A audit` from `K0` plus the split item for `1.A`.
2. Create `1.A ask/planning` from `1.A audit`.
3. The team shapes `1.A`, confirms frame, and confirms spec.
4. The user clicks `Finish Task`.
5. `1.A execution` runs and finishes at `SHA_A`.
6. `1.A audit` becomes chat-enabled.
7. In `1.A audit`, local review compares:
   - initial SHA from `K0`
   - head SHA `SHA_A`
8. If accepted, `1.A audit` produces:
   - accepted summary for `1.A`
   - `SHA_A`
9. The review node updates checkpoint `K0` to checkpoint `K1`.

### 1.B

10. Only after `K1` exists do we create `1.B audit`.
11. `1.B audit` is seeded from:
   - checkpoint `K1`
   - the split item for `1.B`
12. Create `1.B ask/planning` from `1.B audit`.
13. `1.B` now begins with official knowledge of what `1.A` achieved and the accepted SHA after `1.A`.
14. `1.B` goes through the same pattern:
   - confirm frame
   - confirm spec
   - `Finish Task`
   - execution
   - local review in `1.B audit`
15. If accepted, the review node updates to checkpoint `K2`.

### 1.C

16. Only after `K2` exists do we create `1.C audit` and `1.C ask/planning`.
17. `1.C` starts from the accepted subtree context after `1.A` and `1.B`.
18. `1.C` completes the same shaping, execution, and local review flow.

### Final rollup

19. After the last child is accepted, the review node performs rollup review across the realized subtree.
20. The review node emits:
   - accepted rollup summary
   - final subtree SHA
21. That result is handed upward to the parent.

## Deferred Topics

The following topics are intentionally left for later documents:

- exact persistence structure
- route and API surface
- exact git checkpoint mechanics
- failure recovery and restart semantics
- concurrency and locking behavior
- future support for alternative split attempts

## Summary

This model treats:

- `ask/planning` as the place where uncertainty is explored
- confirmed frame and spec as the execution contract
- `execution` as an explicit post-`Finish Task` phase
- `audit` as the official record before execution and the local-review room after execution
- review nodes as the bridge between sequential children and parent intent
- accepted summary plus SHA as the proper handoff unit

The model favors stable intent, clear review boundaries, and sequential checkpointed execution.
