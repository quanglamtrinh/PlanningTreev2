# Phase 0 Contract Review Checklist

Mark each item complete only when the active spec and fixture set support backend and frontend implementation without guesswork.

## Schema

- [ ] `ConversationItem` kinds are frozen
- [ ] required vs optional fields are frozen for every kind
- [ ] `message.role` is frozen as `user | assistant | system`
- [ ] `PendingUserInputRequest` schema is frozen
- [ ] Python and TypeScript mirror requirement is explicitly documented

## Patch Contract

- [ ] `ItemPatch` kinds are frozen
- [ ] `Append` vs `Replace` semantics are explicitly defined
- [ ] immutable fields are listed
- [ ] patch-on-missing-item behavior is frozen
- [ ] `outputFilesReplace` is documented as authoritative final file list

## API And SSE

- [ ] public `GET /threads/{role}` ensure-and-read semantics are frozen
- [ ] `POST /turns` request and response shape are frozen
- [ ] `POST /requests/{request_id}/resolve` request and response shape are frozen
- [ ] `thread.snapshot` payload is frozen
- [ ] `conversation.item.upsert` payload is frozen
- [ ] `conversation.item.patch` payload is frozen
- [ ] `thread.lifecycle` payload is frozen
- [ ] user-input companion event payloads are frozen
- [ ] `thread.error` payload is frozen

## Lifecycle

- [ ] `beginTurn` and `completeTurn` sequencing is frozen
- [ ] `turn/completed` success mapping is frozen
- [ ] `turn/completed` waiting-user-input mapping is frozen
- [ ] `turn/completed` failure or interrupted mapping is frozen

## Identity

- [ ] typed tool item id is frozen as canonical tool identity
- [ ] provisional raw tool-call collapse rule is frozen
- [ ] `requestId` vs `itemId` user-input bridge rule is frozen

## Metadata Sync

- [ ] metadata-bearing mutations are listed
- [ ] `thread.snapshot` is frozen as the only metadata sync primitive
- [ ] repair-on-read behavior for `GET /threads/{role}` is frozen

## Audit Cutover

- [ ] frame audit record path is listed as a V1 writer to migrate
- [ ] spec audit record path is listed as a V1 writer to migrate
- [ ] rollup package audit path is listed as a V1 writer to migrate
- [ ] Phase 5 gate explicitly blocks production cutover if any V1 audit writer remains

## Fixtures

- [ ] every required event class has a captured payload or a documented blocker
- [ ] blocker fields are logged in `open-questions.md`
- [ ] fixture manifest and raw event sample file are current
