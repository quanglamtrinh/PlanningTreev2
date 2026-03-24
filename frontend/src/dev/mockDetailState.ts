import type { DetailState } from '../api/types'

/**
 * Dev-only overlays for Git checkpoint UI. Enable with:
 * `VITE_MOCK_DETAIL_STATE=1` and optionally `VITE_MOCK_GIT_SCENARIO=full|blocked|notpresent`
 */
const SCENARIO = (import.meta.env.VITE_MOCK_GIT_SCENARIO ?? 'full') as 'full' | 'blocked' | 'notpresent'

const overlayFull: Partial<DetailState> = {
  git_ready: true,
  git_blocker_message: null,
  can_finish_task: true,
  spec_confirmed: true,
  initial_sha: 'sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
  head_sha: 'sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb',
  current_head_sha: 'sha256:cccccccccccccccccccccccccccccccccccccccc',
  commit_message: 'pt(1.1): implement auth guard',
  task_present_in_current_workspace: true,
  changed_files: [
    { path: 'src/auth/guard.ts', status: 'A' },
    { path: 'src/auth/types.ts', status: 'M' },
    { path: 'legacy/old.ts', status: 'D' },
    {
      path: 'src/auth/session.ts',
      status: 'R',
      previous_path: 'src/session.ts',
    },
  ],
}

const overlayBlocked: Partial<DetailState> = {
  ...overlayFull,
  git_ready: false,
  git_blocker_message:
    'Working tree is not clean. Commit or discard changes before running this task.',
  can_finish_task: false,
}

const overlayNotPresent: Partial<DetailState> = {
  ...overlayFull,
  task_present_in_current_workspace: false,
  current_head_sha: 'sha256:dddddddddddddddddddddddddddddddddddddddd',
}

function scenarioOverlay(): Partial<DetailState> {
  switch (SCENARIO) {
    case 'blocked':
      return overlayBlocked
    case 'notpresent':
      return overlayNotPresent
    default:
      return overlayFull
  }
}

export function mergeMockDetailState(state: DetailState): DetailState {
  if (!import.meta.env.DEV || import.meta.env.VITE_MOCK_DETAIL_STATE !== '1') {
    return state
  }
  const overlay = scenarioOverlay()
  return {
    ...state,
    ...overlay,
    node_id: state.node_id,
    changed_files: overlay.changed_files ?? state.changed_files,
  }
}
