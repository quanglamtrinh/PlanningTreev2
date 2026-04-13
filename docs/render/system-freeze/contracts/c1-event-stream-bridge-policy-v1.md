# C1 Event Stream Bridge Policy v1

Status: Transitional compatibility policy.

## Goal

Prevent producer/consumer breakage while migrating from legacy envelope fields to canonical C1 fields.

Applies to both C1 envelope classes:

- business frame envelope (`c1-event-stream-envelope-v1.schema.json`)
- control frame envelope (`c1-event-stream-control-envelope-v1.schema.json`)

## Legacy -> Canonical Mapping

- `eventId` -> `event_id` (business frames; optional for control frames)
- `type` -> `event_type`
- `threadRole` + thread binding context -> `thread_id` (until explicit thread ID is emitted)
- `snapshotVersion` -> `snapshot_version`
- `occurredAt` (ISO timestamp) -> `occurred_at_ms` (epoch ms)

## Migration Policy

1. Producer transition:
   - During migration window, producer may emit both canonical and legacy aliases.
   - Canonical fields are source of truth when both are present.
   - Control frames may omit `event_id` by design.
2. Consumer transition:
   - Consumer accepts canonical first, then falls back to mapped legacy fields.
   - Missing canonical+legacy required data is hard error.
   - Control-frame `event_id` remains optional and must not gate parsing.
3. Exit policy:
   - Legacy-only payloads are not allowed after C1 cutover completion.

## Cutover Readiness Criteria

- canonical field coverage reaches 100% in compatibility tests
- no consumer path depends on legacy-only field names
- replay and reconnect tests pass with canonical-only envelopes
