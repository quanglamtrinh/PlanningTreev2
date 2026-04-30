# Codex App-Server MCP Protocol Matrix

This matrix is the PlanningTree implementation source of truth for proxying MCP through Codex app-server. It was verified against `codex-rs/app-server-protocol/src/protocol/common.rs`, `codex-rs/app-server-protocol/src/protocol/v2.rs`, and `codex-rs/app-server/src/codex_message_processor.rs`.

## Client Requests

| Capability | JSON-RPC method | Params | Response | Notes |
| --- | --- | --- | --- | --- |
| Reload MCP servers from latest Codex config | `config/mcpServer/reload` | `undefined` / omitted params | `McpServerRefreshResponse {}` | App-server loads latest config, serializes configured MCP servers into `McpServerRefreshConfig`, and queues refresh per Codex thread. The refresh is applied by Codex on the next active turn rather than eagerly rebuilding every thread. |
| List MCP server status | `mcpServerStatus/list` | `ListMcpServerStatusParams { cursor?: string | null, limit?: number | null, detail?: "full" | "toolsAndAuthOnly" | null }` | `ListMcpServerStatusResponse { data: McpServerStatus[], nextCursor: string | null }` | Reads latest config and returns configured/effective/plugin/built-in server names, tools, resources, resource templates, and auth status. This is config/effective-runtime scoped, not global registry truth. |
| Read MCP resource | `mcpServer/resource/read` | `McpResourceReadParams { threadId: string, server: string, uri: string }` | `McpResourceReadResponse { contents: McpResourceContent[] }` | Requires a loaded Codex thread. App-server dispatches to that thread's MCP connection manager via `CodexThread::read_mcp_resource`. |
| Call MCP server tool | `mcpServer/tool/call` | `McpServerToolCallParams { threadId: string, server: string, tool: string, arguments?: JsonValue, _meta?: JsonValue }` | `McpServerToolCallResponse { content: JsonValue[], structuredContent?: JsonValue, isError?: boolean, _meta?: JsonValue }` | Requires a loaded Codex thread. App-server dispatches to that thread via `CodexThread::call_mcp_tool`. |
| Start MCP OAuth login | `mcpServer/oauth/login` | `McpServerOauthLoginParams { name: string, scopes?: string[] | null, timeoutSecs?: number | null }` | `McpServerOauthLoginResponse { authorizationUrl: string }` | Only supported for streamable HTTP servers. Completion is delivered asynchronously through a server notification. |

## Server Notifications

| Notification | Payload | Notes |
| --- | --- | --- |
| `item/mcpToolCall/progress` | `McpToolCallProgressNotification { threadId, turnId, itemId, message }` | Turn-scoped progress for MCP tool calls. PlanningTree already accepts `item/` stream events. |
| `mcpServer/oauthLogin/completed` | `McpServerOauthLoginCompletedNotification { name, success, error }` | Emitted after the OAuth login task completes or fails. Not thread-scoped. |
| `mcpServer/startupStatus/updated` | `McpServerStatusUpdatedNotification { name, status, error }` where `status` is `starting | ready | failed | cancelled` | Runtime startup status. In PlanningTree, this must be displayed as selected-thread/effective-config status or last-known status, not global registry truth. |

## Server Requests

| Server request | Params | Response | Notes |
| --- | --- | --- | --- |
| `mcpServer/elicitation/request` | `McpServerElicitationRequestParams` | `McpServerElicitationRequestResponse` | Codex uses this when an MCP server elicits user input. PlanningTree already routes it through pending server requests, but UI must support richer schemas and response actions. |

Related non-MCP server requests already sharing the pending-request path: `item/tool/requestUserInput`, `item/commandExecution/requestApproval`, `item/fileChange/requestApproval`, and `item/permissions/requestApproval`.

## Config Apply, Refresh, And Thread Scope Findings

- Codex app-server `config/mcpServer/reload` has no params. It loads the latest Codex config itself and queues `McpServerRefreshConfig` on the internal thread manager.
- PlanningTree applies the thread-scoped effective MCP config by calling `config/batchWrite` with `keyPath: "mcp_servers"`, `mergeStrategy: "replace"`, and `reloadUserConfig: true`, then calls `config/mcpServer/reload` before `turn/start`.
- `McpServerRefreshConfig` contains serialized `mcp_servers` and `mcp_oauth_credentials_store_mode`.
- App-server comments state refresh requests are queued per thread and each thread rebuilds MCP connections on its next active turn.
- The public app-server API does not expose a direct request parameter for an arbitrary per-thread MCP config. PlanningTree must therefore apply a PlanningTree-scoped effective config at the controlled `turn_start` boundary and guard against conflicting active configs because the written Codex user config is shared.
- PlanningTree stores `mcpConfigHash` only as internal runtime/journal metadata. It does not send this hash to provider `turn/start`, and it does not persist full effective config in metadata because that config may contain environment names, headers, or args that should not be exposed in UI/journal/event payloads.
- PlanningTree scopes its last-applied MCP config cache to the Codex app-server process generation. If the app-server restarts, PlanningTree must reapply config even when the requested hash matches the previous in-memory value.
- If `config/batchWrite` succeeds but `config/mcpServer/reload` fails, PlanningTree fails the turn start, leaves the applied-hash cache unchanged, and retries the full apply path on the next turn.
- Older app-server binaries that do not support `config/batchWrite` must fail fast with a clear unsupported-version error rather than continuing with stale or unapplied MCP config.

## Unsupported Or Deferred Gaps

- No direct app-server method was found for passing a one-off effective MCP config inside `turn/start` params.
- No direct global registry/install API exists in Codex app-server for PlanningTree's Global MCP Registry. PlanningTree owns that registry and composes it into Codex-compatible config.
- OAuth callback UX can be deferred unless hosted/app MCP servers are required in the first release.
- Runtime status should not be treated as global registry status when thread-scoped profiles produce different effective configs.
