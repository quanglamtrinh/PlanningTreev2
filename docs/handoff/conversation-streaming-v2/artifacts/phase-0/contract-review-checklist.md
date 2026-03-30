# Phase 0 Contract Review Checklist

Mark each item complete only when the active spec and fixture set support backend and frontend implementation without guesswork.

## Schema

- [x] `ConversationItem` kinds are frozen
- [x] required vs optional fields are frozen for every kind
- [x] `message.role` is frozen as `user | assistant | system`
- [x] `PendingUserInputRequest` schema is frozen
- [x] Python and TypeScript mirror requirement is explicitly documented

## Patch Contract

- [x] `ItemPatch` kinds are frozen
- [x] `Append` vs `Replace` semantics are explicitly defined
- [x] immutable fields are listed
- [x] patch-on-missing-item behavior is frozen
- [x] `outputFilesReplace` is documented as authoritative final file list

## API And SSE

- [x] public `GET /threads/{role}` ensure-and-read semantics are frozen
- [x] `POST /turns` request and response shape are frozen
- [x] `POST /requests/{request_id}/resolve` request and response shape are frozen
- [x] `thread.snapshot` payload is frozen
- [x] `conversation.item.upsert` payload is frozen
- [x] `conversation.item.patch` payload is frozen
- [x] `thread.lifecycle` payload is frozen
- [x] user-input companion event payloads are frozen
- [x] `thread.error` payload is frozen

## Lifecycle

- [x] `beginTurn` and `completeTurn` sequencing is frozen
- [x] `turn/completed` success mapping is frozen
- [x] `turn/completed` waiting-user-input mapping is frozen
- [x] `turn/completed` failure or interrupted mapping is frozen

## Identity

- [x] typed tool item id is frozen as canonical tool identity
- [x] provisional raw tool-call collapse rule is frozen
- [x] `requestId` vs `itemId` user-input bridge rule is frozen

## Metadata Sync

- [x] metadata-bearing mutations are listed
- [x] `thread.snapshot` is frozen as the only metadata sync primitive
- [x] repair-on-read behavior for `GET /threads/{role}` is frozen

## Audit Cutover

- [x] frame audit record path is listed as a V1 writer to migrate
- [x] spec audit record path is listed as a V1 writer to migrate
- [x] rollup package audit path is listed as a V1 writer to migrate
- [x] Phase 5 gate explicitly blocks production cutover if any V1 audit writer remains

## Fixtures

- [x] every required event class has a captured payload or a documented blocker
- [x] blocker fields are logged in `open-questions.md`
- [x] fixture manifest and raw event sample file are current
