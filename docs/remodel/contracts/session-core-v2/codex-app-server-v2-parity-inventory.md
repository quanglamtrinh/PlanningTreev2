# Codex App-Server V2 Parity Inventory

Source of truth: `C:/Users/Thong/codex/codex-rs/app-server-protocol/src/protocol/common.rs`.

PlanningTree supports a focused subset of Codex app-server v2 below `threadId`.
Supported methods must be forwarded with Codex parameter names only; unsupported
methods must be explicit, not re-modeled as PlanningTree lifecycle.

## Supported Client Methods

- `initialize`
- `thread/start`
- `thread/resume`
- `thread/fork`
- `thread/list`
- `thread/loaded/list`
- `thread/read`
- `thread/turns/list`
- `thread/unsubscribe`
- `thread/inject_items`
- `model/list`
- `turn/start`
- `turn/steer`
- `turn/interrupt`

## Explicitly Unsupported Client Methods

PlanningTree does not yet expose archival, naming, metadata, memory-mode, rollback,
realtime, filesystem, account, config, plugin, MCP, one-off command, or marketplace
methods from Codex app-server v2. The canonical list for tests lives in
`backend/session_core_v2/protocol/parity_inventory.py`.

## Supported Server Notifications

- `error`
- `thread/started`
- `thread/status/changed`
- `thread/closed`
- `thread/tokenUsage/updated`
- `turn/started`
- `turn/completed`
- `item/started`
- `item/completed`
- `item/agentMessage/delta`
- `item/plan/delta`
- `item/commandExecution/outputDelta`
- `item/commandExecution/terminalInteraction`
- `item/fileChange/outputDelta`
- `serverRequest/created`
- `serverRequest/updated`
- `serverRequest/resolved`
- `warning`

## Known Notification Gaps

Current deliberate gaps include `thread/compacted`, `turn/diff/updated`,
`turn/plan/updated`, `item/mcpToolCall/progress`,
`item/autoApprovalReview/*`, `rawResponseItem/completed`, `hook/*`,
realtime notifications, and account/config/filesystem side-channel updates.
