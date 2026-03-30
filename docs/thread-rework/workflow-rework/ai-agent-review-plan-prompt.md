# AI Agent Prompt For Thread/Workflow Rework Review And Planning

Status: draft prompt. Use this when you want an AI agent to read the rework docs, review the current codebase, and produce a concrete implementation plan before coding.

## Prompt

```text
You are a senior staff engineer and a tech lead reviewing a planned rework in PlanningTreeMain.

Your job is to:
1. Read the docs listed below carefully.
2. Review the current implementation in the repo.
3. Identify design gaps, inconsistencies, migration risks, and hidden dependencies.
4. Recommend better approaches or targeted improvements when the current proposal can be made meaningfully stronger.
5. Produce one concrete phased implementation plan for the rework.

Do not implement code yet unless explicitly asked later. This task is review + planning only.

Important planning constraints

- Split the work into multiple phases to protect quality and verification at each phase.
- Prefer incremental cut points with clear validation and rollback boundaries.
- Do not propose a big-bang rewrite unless you can prove it is lower risk.
- Do not spend plan complexity on persisted data migration. Current data is mock data, so backward data migration is not required for this rework.

Primary objective

We want to rework:
- the execution model
- the audit model
- the workflow between execution and audit
- the core thread/transcript behavior

Target direction:
- make execution and review transcript behavior feel as close as practical to CodexMonitor
- keep PTM-specific workflow correctness backend-owned
- separate transcript lane vs workflow lane vs metadata lane
- make execution a normal live thread from the transcript point of view
- make local review a normal app-server review thread from the transcript point of view
- keep audit lineage thread as canonical node context, not the primary live review transcript

Primary docs to read first

- docs/thread-rework/workflow-rework/execution-audit-redesign-overview.md
- docs/thread-rework/workflow-rework/execution-audit-workflow-spec.md
- docs/thread-rework/workflow-rework/execution-audit-api-internal-contract-spec.md
- docs/thread-rework/workflow-rework/execution-thread-redesign-spec.md
- docs/thread-rework/workflow-rework/audit-thread-redesign-spec.md

Important supporting docs

- docs/specs/conversation-streaming-v2.md
- docs/handoff/conversation-streaming-v2/phase-6-execution-audit-cutover.md
- docs/specs/gating-rules-matrix.md
- docs/reference/thread-techniques.md
- docs/reference/rich-message-techniques.md

CodexMonitor parity reference

For CodexMonitor parity, do not rely on PTM docs that describe CodexMonitor behavior as the primary source.

Instead, inspect the actual CodexMonitor codebase directly.

Preferred reference repo:
- `Thong/CodexUI/CodexMonitor`

If that repo is not directly available in the environment, use the local CodexMonitor checkout available here:
- `C:/Users/Thong/CodexMonitor_tmp`

Priority CodexMonitor reference files:
- `C:/Users/Thong/CodexMonitor_tmp/src/types.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/app/hooks/useAppServerEvents.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/threads/hooks/useThreadItemEvents.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/threads/hooks/threadReducer/threadItemsSlice.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/utils/threadItems.conversion.ts`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/messages/components/Messages.tsx`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/messages/components/MessageRows.tsx`
- `C:/Users/Thong/CodexMonitor_tmp/src/features/messages/components/useMessagesViewState.ts`

Use CodexMonitor as the primary parity reference for:
- transcript hydration shape
- raw event routing
- reducer merge behavior
- item identity/update semantics
- view-state separation from canonical item state
- reconnect/resume behavior
- working indicator and message/tool presentation patterns

Do not let CodexMonitor override PTM-specific workflow rules, Git semantics, or lane-decision ownership.

Current code areas to inspect

Backend workflow and orchestration:
- backend/services/finish_task_service.py
- backend/services/review_service.py
- backend/services/execution_gating.py
- backend/storage/execution_state_store.py
- backend/storage/review_state_store.py
- backend/services/thread_lineage_service.py

Backend transcript/runtime layer:
- backend/conversation/services/thread_runtime_service.py
- backend/conversation/services/thread_query_service.py
- backend/conversation/services/thread_transcript_builder.py
- backend/conversation/services/thread_history_importer.py
- backend/conversation/projector/thread_event_projector.py
- backend/conversation/storage/thread_snapshot_store_v2.py
- backend/conversation/storage/thread_registry_store.py
- backend/ai/codex_client.py

Frontend state and rendering:
- frontend/src/features/conversation/BreadcrumbChatViewV2.tsx
- frontend/src/features/conversation/state/threadStoreV2.ts
- frontend/src/features/conversation/state/applyThreadEvent.ts
- frontend/src/features/conversation/state/threadEventRouter.ts
- frontend/src/features/conversation/state/workflowEventBridge.ts
- frontend/src/features/conversation/components/ConversationFeed.tsx
- frontend/src/features/conversation/components/useConversationViewState.ts
- frontend/src/features/conversation/components/ToolRow.tsx
- frontend/src/features/conversation/components/ReasoningRow.tsx
- frontend/src/features/conversation/components/WorkingIndicator.tsx

Tests and rollout references to inspect

- backend/tests/integration/test_phase6_execution_audit_cutover.py
- backend/tests/integration/test_chat_v2_api.py
- backend/tests/integration/test_review_api.py
- backend/tests/unit/test_thread_readonly.py
- backend/tests/unit/test_execution_gating.py
- backend/tests/unit/test_node_detail_service_audit_v2.py
- frontend/tests/unit/threadStoreV2.test.ts
- frontend/tests/unit/workflowEventBridge.test.tsx
- frontend/tests/unit/BreadcrumbChatViewV2.test.tsx

Non-negotiable design rules you must preserve while reviewing

- Transcript live path should be raw app-server event -> client reducer -> UI.
- Transcript reload path should be client thread service -> thread/read -> hydrate local state.
- PTM should not keep backend-projected per-delta transcript snapshots as the target model for execution/review.
- Backend remains authoritative for workflow correctness, CTA gating, run/review-cycle persistence, drift checks, commit decisions, and reconciliation.
- Execution remains writable for follow-up implement turns in execution_decision_pending.
- Audit generic composer remains disabled in standard workflow mode.
- Audit lineage thread remains canonical node context.
- First local review creates a detached review thread from the audit lineage thread.
- Later local reviews reuse the same review thread.
- Review runtime must be read-only and runtime-enforced.
- Improve in Execution v1 uses exitedReviewMode.review.
- If commit succeeded but review/start failed, retry must reuse the same reviewCommitSha.
- First detached retry must reconcile by clientRequestId before trying detached creation again.
- Workflow validation must use both the current decision object and the source run/review-cycle record.
- Single-instance and single-window support in v1 is a product constraint, not a temporary assumption.

What I want from you

Review the docs and the current codebase and answer these questions:

1. What is the current architecture and behavior today for:
   - execution thread
   - audit thread / review flow
   - transcript hydration
   - live transport
   - workflow-state and CTA gating
   - retry/reconciliation

2. Where does the current implementation conflict with the target docs?

3. Where do the docs themselves still have ambiguity, overlap, or contradictions?

4. Where can the target proposal be improved beyond the current docs?
   - simpler architecture
   - lower-risk sequencing
   - better ownership boundaries
   - clearer contracts
   - better parity with CodexMonitor where that improves the design
   - better UX/runtime behavior without violating PTM workflow requirements

5. What is the smallest safe migration path from current state to target state?

6. What should be implemented first, second, and third, and why?

7. How should the work be broken into enough phases that each phase can be implemented, tested, and stabilized with high confidence before moving on?

8. What are the highest-risk areas:
   - artifact drift and commit semantics
   - decision supersession
   - detached review-thread adoption
   - hydration and refresh correctness
   - requestUserInput handling
   - readonly review enforcement
   - legacy V1/V2 coexistence during migration

9. What tests, instrumentation, and rollout gates are required before shipping?

How to work

- Do not just summarize docs.
- Compare docs against actual code paths and current tests.
- Call out where the repo already partially implements the target architecture.
- Call out where legacy assumptions still exist and would block the redesign.
- Use actual CodexMonitor code as the parity reference, not PTM docs summarizing CodexMonitor.
- If you recommend a better design than what is currently written in the docs, make that explicit and explain the tradeoff.
- Distinguish between:
  - must-change now
  - safe transitional layer
  - can defer until later
- Assume schema and persisted data can change freely if that simplifies the rework, as long as code correctness and phase quality remain strong.
- Prefer concrete references to files, services, stores, reducers, routes, and tests.
- Reference specific file paths and line numbers whenever possible.
- If a conclusion is inferred rather than explicitly stated in a doc or file, label it as an inference.

Required output format

Produce the response in the following structure:

1. Executive summary
   - 5-10 bullets max
   - focus on the most important findings

2. Current-state architecture map
   - backend control plane
   - backend transcript/runtime layer
   - frontend transcript/hydration/view-state layer
   - workflow and gating layer
   - where execution/audit currently diverge from the target

3. Findings
   - list concrete issues, gaps, or ambiguities
   - order by severity
   - for each finding include:
     - title
     - why it matters
     - impacted files/docs
     - whether it is a doc gap, code gap, or migration risk

4. Improvement opportunities
   - list places where the target design can be improved
   - distinguish:
     - strong recommendation
     - optional improvement
     - nice-to-have
   - explain why the improvement is better than the current draft

5. Recommended target implementation shape
   - short section describing the intended end-state architecture
   - keep it consistent with the docs unless you found a strong reason to recommend a doc change
   - if you recommend changing the docs, say exactly what should change

6. Phased implementation plan
   - use as many phases as needed to keep each phase safe and reviewable
   - default shape can start from:
     - Phase 1: foundation
     - Phase 2: backend workflow and reconciliation changes
     - Phase 3: frontend hydration/transport/thread UI changes
     - Phase 4: audit lineage/review-thread split
     - Phase 5: rollout, cleanup, and guardrails
   - you may split these into more phases if that improves safety, testability, or sequencing clarity
   - for each phase include:
     - objective
     - exact code areas to change
     - dependencies
     - key risks
     - tests to add or update
     - clear exit criteria
     - why this phase boundary is the right quality checkpoint

7. Open questions / decisions to resolve
   - only include real decisions that materially affect implementation or sequencing

8. Ship checklist
   - tests
   - instrumentation / logging
   - migration guards
   - rollback considerations

Quality bar

- Be critical and specific.
- Prefer one strong, actionable plan over multiple vague options.
- Do not hand-wave with "refactor as needed".
- Make the sequence realistic for an incremental migration in a real repo.
- Bias toward more, smaller phases when that meaningfully improves verification quality.
- Do not require a data migration plan unless you find a truly unavoidable persisted contract issue outside the current mock data.
- Recommend a better design when warranted; do not limit yourself to defending the current docs if a clearer or safer approach exists.
- When borrowing from CodexMonitor, ground the recommendation in actual repo code patterns, not second-hand descriptions.
- Explicitly call out any place where the target docs may require adjustment before implementation starts.
```

## Notes

- The prompt is intentionally written in English because the spec names, code paths, and architecture terms in this repo are English.
- If you want, the agent's response can still be requested in Vietnamese.
