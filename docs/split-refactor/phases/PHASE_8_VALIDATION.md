# Phase 8 Validation

Last updated: 2026-03-18

## Validation Commands Run

```powershell
.\\.venv\\Scripts\\python.exe -m pytest backend/tests/unit/test_split_prompt_builder.py backend/tests/unit/test_split_contract.py backend/tests/unit/test_split_service.py backend/tests/integration/test_split_api.py -q
Push-Location frontend
npm.cmd exec vitest run tests/unit/ConversationSurface.test.tsx
Pop-Location
npm.cmd --prefix frontend run typecheck
```

## Evidence Matrix

| Item | Evidence | Command | Expected result |
| --- | --- | --- | --- |
| `P8.1` | `backend/tests/unit/test_split_prompt_builder.py`:`test_build_generation_prompt_includes_context_count_and_shared_schema`; `test_build_planning_base_instructions_mentions_only_canonical_modes`; `test_build_planning_base_instructions_includes_mode_specific_semantics` | backend pytest command above | Passes and proves all 4 canonical modes are covered for prompt generation, base instructions, and mode semantics. |
| `P8.2` | `backend/tests/unit/test_split_prompt_builder.py`:`test_validate_split_payload_accepts_valid_canonical_payload`; `test_validate_split_payload_enforces_mode_specific_counts`; `test_split_payload_issues_rejects_extra_top_level_and_item_keys`; `test_split_payload_issues_rejects_missing_blank_and_duplicate_fields`; `test_parse_generation_response_normalizes_exact_canonical_payload`; `test_parse_generation_response_rejects_legacy_slice_shape`; `test_parse_generation_response_rejects_extra_keys_and_invalid_text`; `test_build_hidden_retry_feedback_includes_schema_issues_and_mode_count` | backend pytest command above | Passes and proves strict canonical parsing, validation, count bounds, extra-key rejection, legacy-shape rejection, and retry feedback. |
| `P8.3` | `backend/tests/unit/test_split_contract.py`:`test_canonical_split_mode_registry_preserves_metadata`; `backend/tests/unit/test_split_service.py`:`test_apply_split_payload_materializes_all_canonical_modes_through_flat_family` | backend pytest command above | Passes and proves canonical registry metadata plus `flat_subtasks_v1` materialization for all canonical modes, including child order, purpose, revision 1, output family, and stable mapping. |
| `P8.4` | `backend/tests/unit/test_split_service.py`:`test_apply_split_payload_materialization_is_shared_across_canonical_modes_with_same_output_family` | backend pytest command above | Passes and proves service-level materialization depends on shared flat-family data rather than mode-specific payload behavior. |
| `P8.9.a` | `backend/tests/unit/test_split_service.py`:`test_split_service_requires_confirmation_for_resplit`; `backend/tests/integration/test_split_api.py`:`test_split_api_requires_confirmation_for_resplit` | backend pytest command above | Passes and proves replace requires `confirm_replace` at both service and API boundaries. |
| `P8.9.b` | `backend/tests/unit/test_split_service.py`:`test_split_service_replace_lifecycle_preserves_canonical_metadata_and_planning_history` | backend pytest command above | Passes and proves confirmed replace supersedes prior children and activates a new branch. |
| `P8.9.c` | `backend/tests/unit/test_split_service.py`:`test_split_service_replace_lifecycle_preserves_canonical_metadata_and_planning_history` | backend pytest command above | Passes and proves parent `planning_mode` remains canonical after replace. |
| `P8.9.d` | `backend/tests/unit/test_split_service.py`:`test_split_service_replace_lifecycle_preserves_canonical_metadata_and_planning_history` | backend pytest command above | Passes and proves stable `split_metadata` survives replace, including `mode`, `output_family`, `source`, `warnings`, child ids, revision, and canonical materialization. |
| `P8.9.e` | `backend/tests/unit/test_split_service.py`:`test_split_service_replace_lifecycle_preserves_canonical_metadata_and_planning_history`; `frontend/tests/unit/ConversationSurface.test.tsx`:`renders split replace history with current canonical cards and a superseded replay branch` | backend pytest command above; frontend Vitest command above | Passes and proves replace history is persisted on the backend and rendered on the frontend with current canonical cards plus superseded replay UI semantics. |

## Validation Coverage

- Remaining Phase 8 items are closed by explicit evidence instead of checklist-only prose.
- Existing prompt-builder, contract, and materialization coverage remains the primary proof source for `P8.1`-`P8.3`.
- New backend coverage closes the service-level invariant and replace lifecycle history proof.
- New frontend coverage closes split-specific replay/render proof after replace.
- Frontend typechecking confirms the Phase 8 test closeout did not require runtime type changes.

## Failures, Warnings, Or Residual Risks

- `ConversationSurface` Vitest still emits pre-existing React warnings about list keys in `ToolCallBlock` and some `act(...)` warnings in execution-surface tests; they do not fail the suite and are outside the split-refactor scope.
- No additional contract or migration risks were discovered during Phase 8 closeout.

## Final Validation Outcome

- Phase 8 is complete when the commands above pass and every remaining checklist item is backed by the Evidence Matrix entries in this document.
