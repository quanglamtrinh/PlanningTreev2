# Ask Queue Risk Baseline v1

Status: Frozen for ask migration.

Last updated: 2026-04-14.

## 1. Risk Triggers Requiring Confirmation (Frozen)

An ask queue entry must transition to `requires_confirmation` before send when any trigger is true:

1. Entry age exceeds threshold:
   - `now_ms - createdAtMs > 90_000`
2. Ask context drift is detected:
   - ask thread reset occurred after enqueue, or
   - entry context marker no longer matches current ask thread context
3. Explicit policy marks entry as stale:
   - policy engine emits stale marker for the entry

## 2. Safety Invariants (Frozen)

1. `requires_confirmation` entries are never auto-sent.
2. Explicit user confirmation is required to re-qualify entry for send.
3. Confirm action re-queues the entry to `queued` with refreshed enqueue context.

## 3. Baseline Risk Controls

1. Auto-flush only evaluates entries in `queued`.
2. `failed` entries require explicit retry.
3. Risk policy must not change execution lane confirmation behavior.

## 4. Relation to Reset Policy

1. Ask reset clears queue entries by contract.
2. Cleared entries are not implicitly confirmed or re-enqueued after reset.

