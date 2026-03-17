# Phase 6 Open Issues

## Summary Table
| Issue ID | Title | Affected Subphase | Classification | Status |
| --- | --- | --- | --- | --- |
| `P6-OI-005` | Compatibility inventory not yet classified for cleanup | `6.3` | Blocking | Open |

## Resolved In 6.1
| Issue ID | Title | Affected Subphase | Resolution status |
| --- | --- | --- | --- |
| `P6-OI-001` | Baseline performance evidence not yet recorded | `6.1` | Resolved on `2026-03-17` |
| `P6-OI-002` | Dense-event corpus and thresholds not yet locked | `6.1` | Resolved on `2026-03-17` |

## Resolved In 6.2
| Issue ID | Title | Affected Subphase | Resolution status |
| --- | --- | --- | --- |
| `P6-OI-003` | Concurrency isolation matrix not yet proven | `6.2` | Resolved on `2026-03-17` |
| `P6-OI-004` | Reconnect and replay stress proof not yet complete | `6.2` | Resolved on `2026-03-17` |

## Phase 6.3

### `P6-OI-005` - Compatibility inventory not yet classified for cleanup
- Description:
  - transitional compatibility behavior has not yet been fully inventoried and classified
- Why it matters:
  - cleanup cannot be gate-based if the target set is not known or not classified
- Next action:
  - populate `PHASE_6_CLEANUP_LOG.md` with initial targets and classifications before any removal is considered
