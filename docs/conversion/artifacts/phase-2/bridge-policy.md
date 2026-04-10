# Phase 2 Bridge Policy (V2 -> V3 Read Compatibility)

## Env Controls (Env-Only)
- `PLANNINGTREE_CONVERSATION_V3_BRIDGE_MODE`
  - accepted: `enabled | allowlist | disabled`
  - invalid/missing -> defaults to `enabled`
- `PLANNINGTREE_CONVERSATION_V3_BRIDGE_ALLOWLIST`
  - comma-separated `project_id` list
  - parser trims whitespace and drops empty entries

## Query Behavior (`ThreadQueryServiceV3.get_thread_snapshot`)
1. Validate access/binding.
2. Read `conversation_v3/{node}/{thread_role}.json`.
3. If V3 snapshot exists:
   - read/repair in V3 only.
4. If V3 snapshot is missing:
   - `disabled` -> throw `conversation_v3_missing` (`409`).
   - `allowlist` + project not listed -> throw `conversation_v3_missing` (`409`).
   - otherwise -> read V2 snapshot, convert to canonical V3 (`threadRole`), persist to V3.

## Hard Rule
- No V2 back-write is allowed from V3 query/runtime path.

## Workflow Examples
- Enabled mode:
  - missing V3 snapshot is bridged once from V2, then served from V3.
- Disabled mode:
  - missing V3 snapshot immediately returns typed `conversation_v3_missing`.
- Allowlist mode:
  - only listed projects are allowed temporary read-through; all others fail closed.
