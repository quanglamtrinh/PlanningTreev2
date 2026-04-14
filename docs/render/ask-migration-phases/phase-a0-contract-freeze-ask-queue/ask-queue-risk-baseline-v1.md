# Ask Queue Risk Baseline v1

Status: Frozen for ask migration.

Risk triggers requiring confirmation:

1. Entry age exceeds configured threshold.
2. Ask context drift detected (thread reset/context marker mismatch).
3. Explicit policy gate marks entry as stale.

Safety invariants:

1. requires_confirmation entries are never auto-sent.
2. Explicit user confirm is required before send.
