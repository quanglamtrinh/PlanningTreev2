# Phase 4: Sidebar Entrypoint and UX Polish

Status: not started.

Effort: 9% (about 2.0 engineering days).

Depends on: Phase 3.

## Goal

Integrate discoverable entrypoint in existing sidebar and polish route UX for daily usage.

## Scope

- Keep sidebar button in usage area with current placement under existing usage block.
- Navigate to `/usage-snapshot`.
- Add active-state and hover/focus behavior.
- Ensure accessibility and keyboard navigation.

## Detailed implementation checklist

## 1) Add sidebar button

Update `frontend/src/features/graph/Sidebar.tsx`:

- keep button directly under current usage block (current placement), polish visuals and focus behavior.
- label recommendation:
  - `Usage Snapshot`
- click action:
  - `navigate('/usage-snapshot')`
- include `aria-label` and descriptive title.

## 2) Add style treatment

Update `frontend/src/features/graph/Sidebar.module.css`:

- button visual hierarchy should sit between project tree and footer usage block.
- add active style when current route is `/usage-snapshot`.
- add keyboard focus-visible ring consistent with design tokens.

## 3) Route-aware active state

In `Sidebar.tsx`:

- derive route via `useLocation`.
- compute active class for usage button.
- ensure existing project behaviors remain unchanged.

## 4) UX and accessibility pass

- verify button remains visible when sidebar has many projects.
- verify contrast and focus indicators in available themes.
- verify button is reachable and actionable via keyboard only.

## 5) Sidebar unit test extension

Update `frontend/tests/unit/Sidebar.test.tsx`:

- render sidebar
- click `Usage Snapshot` button
- assert route becomes `/usage-snapshot`

## File targets

- `frontend/src/features/graph/Sidebar.tsx`
- `frontend/src/features/graph/Sidebar.module.css`
- `frontend/tests/unit/Sidebar.test.tsx`

## Verification commands

- `npm run test:unit --prefix frontend -- tests/unit/Sidebar.test.tsx`
- `npm run typecheck --prefix frontend`

## Deliverables

- Users can open Usage Snapshot from current sidebar with one click.
- Sidebar behavior remains stable for existing project flows.

## Exit criteria

- Sidebar entrypoint and route navigation are test-covered and stable.
- No accessibility blocker remains for this new navigation action.
