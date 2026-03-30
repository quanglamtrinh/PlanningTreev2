# Phase 6 Semantic Parity Verification

Status: pending.

Use this document to record evidence that execution and audit V2 surfaces now meet the semantic presentation expectations for Phase 6 closeout.

## Required Checks

- grouped execution or audit tool rendering behaves correctly
- working indicator shows semantic progress labels and timing
- long command output no longer forces destructive scroll-to-bottom
- reasoning items contribute semantic progress labels
- command terminal interaction appears inside canonical tool output
- final file lists still converge through `outputFilesReplace`

## Suggested Commands

- `python -m pytest backend/tests/unit/test_conversation_v2_projector.py backend/tests/integration/test_phase6_execution_audit_cutover.py -q`
- `npm run test:unit --prefix frontend -- BreadcrumbChatViewV2.test.tsx threadStoreV2.test.ts applyThreadEvent.test.ts`

## Evidence Log

- pending

## Notes

- keep this file focused on semantic parity evidence
- transport-only or routing-only evidence should remain in `cutover-checklist.md` or `smoke-results.md`
