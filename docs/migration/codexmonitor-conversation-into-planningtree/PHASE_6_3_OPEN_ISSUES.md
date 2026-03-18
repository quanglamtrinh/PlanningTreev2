# Phase 6.3 Open Issues

## Status
No blocking Phase 6.3 issues remain.

The remaining items are explicitly preserved or blocked follow-up boundaries and do not block Phase 6 closure.

## Carry-Forward Items
| Issue | Classification | Blocking | Summary | Required Decision | Owner Phase |
| --- | --- | --- | --- | --- | --- |
| `P6.3-OI-001` | `preserved_out_of_scope_for_6_3` | No | Ask packet/reset sidecar boundary remains in place so `DeltaContextCard` and packet event UX continue to work | Decide whether packet/reset sidecar stays separate or moves onto a dedicated conversation-owned model | Post-6.3 ask-sidecar cleanup |
| `P6.3-OI-002` | `transitional_but_blocked` | No | Ask reset ownership is still coupled to the preserved packet sidecar boundary | Write an explicit rehoming spec that keeps current semantics unchanged | Post-6.3 ask-sidecar cleanup |
| `P6.3-OI-003` | `preserved_out_of_scope_for_6_3` | No | Graph/split planning history path remains intentionally preserved outside breadcrumb cleanup | Decide a dedicated graph-planning cleanup strategy before removal | Post-6.3 graph-planning cleanup |

## Resolved In Phase 6.3
- Execution visible legacy breadcrumb fallback removal
- Ask visible transcript/session fallback removal
- Breadcrumb planning visible fallback removal
- Execution v1 chat route removal
- Safe visible-host conversation-v2 feature flag retirement
