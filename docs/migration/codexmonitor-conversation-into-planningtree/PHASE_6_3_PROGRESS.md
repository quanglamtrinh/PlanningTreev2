# Phase 6.3 Progress

## Overall Status
Complete.

## Batch Board
| Batch | Status | Notes |
| --- | --- | --- |
| `P6.3.a` | Complete | Cleanup inventory, caller audit, and preserved-boundary audit recorded |
| `P6.3.b` | Complete | Execution visible legacy fallback removed; retired v1 chat route family removed |
| `P6.3.c` | Complete | Ask visible legacy fallback removed; packet/reset sidecar preserved |
| `P6.3.d` | Complete | Breadcrumb planning fallback removed; graph/split planning path preserved |
| `P6.3.e` | Complete | Import-ban/search validation, route absence proof, and docs closeout complete |

## What Landed
- `ChatPanel`, `AskPanel`, and `PlanningPanel` are now conversation-v2-only host panels
- `BreadcrumbWorkspace` no longer gates visible hosts behind conversation-v2 feature flags
- `chat-store.ts`, `featureFlags.ts`, legacy breadcrumb panels, and `legacyConversationAdapter.ts` were removed
- `ask-store.ts` now owns only packet/reset sidecar state
- `backend/routes/chat.py` is no longer part of the public backend surface
- `scripts/check_phase6_3_cleanup.py` now enforces removal and preserved-boundary assertions

## Preserved For Later Work
- Ask packet/reset sidecar boundary remains preserved out of scope for 6.3
- Ask reset ownership remains blocked pending explicit rehoming
- Graph/split planning history path remains preserved out of scope for 6.3

## Verification Snapshot
- Frontend targeted cleanup and preservation suite: 12 files, 77 tests, passed
- Backend targeted cleanup and gateway suite: 32 tests, passed
- `npm run check:phase6_3_cleanup`: passed
- `npm run typecheck`: passed
- `npm run build`: passed

## Non-Blocking Notes
- React `act(...)` warnings remain in older `GraphWorkspace` and `ConversationSurface` tests
- Vite build reports a chunk-size advisory for the main frontend bundle
- These warnings are recorded but did not block 6.3 closure
