# S1 JSON-RPC Lifecycle Contract v1

Status: Normative

## Scope

Defines connection and handshake lifecycle for Session Core V2.
Transport defaults to stdio JSON-RPC 2.0.

## Handshake sequence

1. Client sends JSON-RPC request `initialize`.
2. Server returns `initialize` response.
3. Session manager sends JSON-RPC notification `initialized`.
4. Connection state transitions to `initialized`.

Any non-handshake request before step 4 must fail with deterministic error:

- code: `ERR_SESSION_NOT_INITIALIZED`
- HTTP mapping (wrapper): `409`

## Initialize parameters (minimum)

`initialize.params` must include:

1. `clientInfo.name` (required)
2. `clientInfo.version` (required)
3. `capabilities.experimentalApi` (optional, default `false`)
4. `capabilities.optOutNotificationMethods` (optional list of exact method names)

## Connection states

Allowed states:

1. `disconnected`
2. `connecting`
3. `initialized`
4. `error`

Allowed transitions:

1. `disconnected -> connecting`
2. `connecting -> initialized`
3. `connecting -> error`
4. `initialized -> disconnected`
5. `initialized -> error`
6. `error -> connecting` (retry path)

No other transitions are allowed.

## REST facade rules

1. `POST /v4/session/initialize` is public and mandatory.
2. `initialized` is an internal protocol transition.
3. `POST /v4/session/initialized` is not exposed publicly by default.
4. Public two-step handshake route is only allowed when a remote external client requires it.

## Capability filtering

When `optOutNotificationMethods` is present:

1. Suppressed methods are filtered before outbound stream fanout.
2. Journal persistence is unchanged for replay-authoritative tiers.
3. Suppression is scoped to connection/subscriber, not thread global state.

## Error envelope

REST façade errors must be deterministic:

```json
{
  "ok": false,
  "error": {
    "code": "ERR_SESSION_NOT_INITIALIZED",
    "message": "Session has not completed initialize/initialized handshake.",
    "details": {}
  }
}
```

