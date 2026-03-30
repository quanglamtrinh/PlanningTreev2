# Phase 0 Fixture Manifest

Status: adapter-captured raw corpus recorded. The rows below now point at replayable `on_raw_event` payloads captured from a fixed `StdioTransport` harness; open questions still track upstream "always" guarantees that exceed the captured sample set.

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
| agent message started | `item/started` | assistant | `item.id`, `threadId`, `turnId` | `item.type=agentMessage` | captured_from_stdio_transport_harness | replayable sample stored in `raw-event-samples.jsonl` |
| agent message delta | `item/agentMessage/delta` | text delta | `itemId`, `threadId`, `turnId` | delta text | captured_from_stdio_transport_harness | sample includes canonical `itemId`; upstream "always" guarantee still tracked in `open-questions.md` |
| agent message completed | `item/completed` | success | `item.id`, `threadId`, `turnId` | terminal status | captured_from_stdio_transport_harness | |
| plan started | `item/started` | plan | `item.id`, `threadId`, `turnId` | `item.type=plan` | captured_from_stdio_transport_harness | |
| plan delta | `item/plan/delta` | text append | `itemId`, `threadId`, `turnId` | delta text | captured_from_stdio_transport_harness | |
| plan completed | `item/completed` | plan | `item.id`, `threadId`, `turnId` | terminal status | captured_from_stdio_transport_harness | |
| reasoning event | `item/reasoning/*` | summary or detail | stable reasoning item id | reasoning text fragment | captured_from_stdio_transport_harness | summary-delta sample captured; upstream identity stability still tracked as an open question |
| command started | `item/started` | commandExecution | `item.id`, `threadId`, `turnId` | `item.type=commandExecution`, `callId` if present | captured_from_stdio_transport_harness | |
| command output delta | `item/commandExecution/outputDelta` | stdout append | `itemId`, `threadId`, `turnId` | output chunk | captured_from_stdio_transport_harness | |
| command completed | `item/completed` | commandExecution | `item.id`, `threadId`, `turnId` | exit code and terminal state | captured_from_stdio_transport_harness | |
| file change started | `item/started` | fileChange | `item.id`, `threadId`, `turnId` | `item.type=fileChange` | captured_from_stdio_transport_harness | |
| file change delta | `item/fileChange/outputDelta` | preview | `itemId`, `threadId`, `turnId` | preview text and optional preview file entries | captured_from_stdio_transport_harness | |
| file change completed | `item/completed` | fileChange | `item.id`, `threadId`, `turnId` | authoritative final file list | captured_from_stdio_transport_harness | sample includes `changes[]`; upstream "always" guarantee still tracked in `open-questions.md` |
| raw tool call | `item/tool/call` | generic | `callId`, `threadId`, `turnId` | tool name and arguments | captured_from_stdio_transport_harness | used only for provisional enrichment |
| user input requested | `item/tool/requestUserInput` | prompt | `itemId`, `requestId`, `threadId`, `turnId` | questions and options | captured_from_stdio_transport_harness | |
| user input resolved | `serverRequest/resolved` | answers submitted | `itemId`, `requestId`, `threadId`, `turnId` | answers and resolved timestamp | captured_from_stdio_transport_harness | sample preserves both identities and timestamps |
| thread status changed | `thread/status/changed` | lifecycle | `threadId` | processing state | captured_from_stdio_transport_harness | |
| turn completed | `turn/completed` | success | `threadId`, `turnId` | outcome, status, error detail if any | captured_from_stdio_transport_harness | |
| turn completed | `turn/completed` | waiting user input | `threadId`, `turnId` | waiting-user-input outcome | captured_from_stdio_transport_harness | |
| turn completed | `turn/completed` | failed or interrupted | `threadId`, `turnId` | failure outcome and terminal detail | captured_from_stdio_transport_harness | captured interrupted sample is used for the failed terminal policy |

## Sign-Off Conditions

- every blocker-marked row has either a real capture or a documented workaround decision
- all identity fields required by the V2 mapping table are verified
- any missing upstream fields are recorded in `open-questions.md`
