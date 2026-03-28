# Phase 0 Fixture Manifest

Status: starter template. Replace `pending` rows with concrete capture status as fixtures are collected.

## Purpose

This manifest tracks the minimum raw upstream payload set required to freeze the V2 contract and support deterministic projector and reducer replay.

## Capture Rules

- each event class should have at least one real captured payload
- capture success and failure variants when the event can terminate differently
- keep the raw payload as close to the upstream transport as possible
- annotate any missing field that must be synthesized locally

## Fixture Matrix

| Event Class | Upstream Method | Variant | Required Identity Fields | Required Contract Fields | Capture Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| agent message started | `item/started` | assistant | `item.id`, `threadId`, `turnId` | `item.type=agentMessage` | pending | |
| agent message delta | `item/agentMessage/delta` | text delta | `itemId`, `threadId`, `turnId` | delta text | pending | blocker if `itemId` absent |
| agent message completed | `item/completed` | success | `item.id`, `threadId`, `turnId` | terminal status | pending | |
| plan started | `item/started` | plan | `item.id`, `threadId`, `turnId` | `item.type=plan` | pending | |
| plan delta | `item/plan/delta` | text append | `itemId`, `threadId`, `turnId` | delta text | pending | |
| plan completed | `item/completed` | plan | `item.id`, `threadId`, `turnId` | terminal status | pending | |
| reasoning event | `item/reasoning/*` | summary or detail | stable reasoning item id | reasoning text fragment | pending | confirm upstream identity stability |
| command started | `item/started` | commandExecution | `item.id`, `threadId`, `turnId` | `item.type=commandExecution`, `callId` if present | pending | |
| command output delta | `item/commandExecution/outputDelta` | stdout append | `itemId`, `threadId`, `turnId` | output chunk | pending | |
| command completed | `item/completed` | commandExecution | `item.id`, `threadId`, `turnId` | exit code and terminal state | pending | |
| file change started | `item/started` | fileChange | `item.id`, `threadId`, `turnId` | `item.type=fileChange` | pending | |
| file change delta | `item/fileChange/outputDelta` | preview | `itemId`, `threadId`, `turnId` | preview text and optional preview file entries | pending | |
| file change completed | `item/completed` | fileChange | `item.id`, `threadId`, `turnId` | authoritative final file list | pending | blocker if final list is absent |
| raw tool call | `item/tool/call` | generic | `callId`, `threadId`, `turnId` | tool name and arguments | pending | used only for provisional enrichment |
| user input requested | `item/tool/requestUserInput` | prompt | `itemId`, `requestId`, `threadId`, `turnId` | questions and options | pending | |
| user input resolved | `serverRequest/resolved` | answers submitted | `itemId`, `requestId`, `threadId`, `turnId` | answers and resolved timestamp | pending | blocker if either identity key absent |
| thread status changed | `thread/status/changed` | lifecycle | `threadId` | processing state | pending | |
| turn completed | `turn/completed` | success | `threadId`, `turnId` | outcome, status, error detail if any | pending | |
| turn completed | `turn/completed` | waiting user input | `threadId`, `turnId` | waiting-user-input outcome | pending | |
| turn completed | `turn/completed` | failed or interrupted | `threadId`, `turnId` | failure outcome and terminal detail | pending | |

## Sign-Off Conditions

- every blocker-marked row has either a real capture or a documented workaround decision
- all identity fields required by the V2 mapping table are verified
- any missing upstream fields are recorded in `open-questions.md`
