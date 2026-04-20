# S4 Event Stream Contract v1

Status: Normative

## Scope

Defines canonical event stream envelopes for Session Core V2.
Method names and parameter shape must remain Codex-native.

## Envelope classes

1. Replayable event envelope:
   - schema: `s4-event-envelope-v1.schema.json`
   - includes `eventId`, `eventSeq`, `tier`, `method`, `params`
2. Server-request envelope:
   - schema: `s4-server-request-envelope-v1.schema.json`
   - represents pending server-initiated request records

## Ordering invariants

1. For one `threadId`, `eventSeq` is strictly monotonic increasing.
2. Cursor progression is based on `eventSeq`.
3. Apply order equals journal order (`eventSeq` ascending).
4. Control and cosmetic events must not break Tier 0 ordering.

## Priority tiers

Tier 0 (lossless via journal + replay):

- `item/started`
- `item/agentMessage/delta`
- `item/plan/delta`
- `item/completed`
- `turn/completed`
- `thread/status/changed`
- `thread/started`
- `thread/closed`
- `serverRequest/resolved`

Tier 1 (merge-safe):

- `item/reasoning/summaryTextDelta`
- `item/reasoning/summaryPartAdded`
- `item/reasoning/textDelta`
- `item/commandExecution/outputDelta`
- `item/fileChange/outputDelta`

Tier 2 (best effort):

- optional diagnostics/progress that are not transcript-critical

## Backpressure rule

Tier 0 guarantee is achieved by journal durability, not producer blocking.
Lagged subscriber behavior:

1. stream reset
2. replay from cursor
3. snapshot resync when cursor expired

## SSE frame format

Events endpoint returns SSE:

```text
id: <eventSeq>
event: <method>
data: <json envelope>
```

`id` is required for replayable envelopes.

## Prohibited behavior

1. Dropping Tier 0 journal events.
2. Emitting replayable envelope without `eventId` and `eventSeq`.
3. Rewriting Codex method names into app-local aliases.
4. Advancing cursor by non-replayable control frames.

