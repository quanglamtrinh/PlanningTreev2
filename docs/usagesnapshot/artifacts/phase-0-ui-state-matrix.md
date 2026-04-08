# Phase 0 UI-State Matrix

Status: completed.

## Route and entrypoint contract

- New route: `/usage-snapshot`
- Entry point: new sidebar button under existing usage block
- Entry action: navigate to `/usage-snapshot` from graph shell

## Screen state matrix

| State | Trigger | Required UI behavior | Retry behavior |
|---|---|---|---|
| loading | first mount before first response | render usage skeleton; hide stale data placeholders | n/a |
| loaded | successful snapshot response with data | render cards, chart, top models, updated timestamp | manual refresh available |
| empty | successful snapshot response with zero meaningful usage | render explicit empty-state message | manual refresh available |
| recoverable_error | request fails but app shell is healthy | render error banner/message and keep route interactive | manual refresh retries |
| refresh_in_progress | polling tick or manual refresh while data exists | keep existing data visible; show refresh affordance as busy | auto/next retry cycle applies |

## Interaction matrix

| Interaction | Expected result |
|---|---|
| click sidebar `Usage Snapshot` button | navigate to `/usage-snapshot` |
| manual refresh click | trigger one immediate fetch cycle |
| polling interval tick | trigger fetch without route change |
| out-of-order response | stale response is ignored via generation guard |
| navigate away from screen | stop applying stale updates to unmounted view |

## Copy and UX boundary

- Keep copy concise and operational:
  - title: `Usage Snapshot`
  - empty state: communicate no session usage yet
  - error state: recoverable fetch failure with retry
- Do not include workspace selector in this track.
- Do not mix account rate-limit widgets into this screen.

## Accessibility baseline

- Sidebar entry button must be keyboard-focusable.
- Button must have `aria-label` and visible focus style.
- Refresh control must expose disabled/busy semantics when request is active.
