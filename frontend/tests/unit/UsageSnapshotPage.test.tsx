import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

type HookState = {
  snapshot: {
    updated_at: number
    days: {
      day: string
      input_tokens: number
      cached_input_tokens: number
      output_tokens: number
      total_tokens: number
      agent_time_ms: number
      agent_runs: number
    }[]
    totals: {
      last7_days_tokens: number
      last30_days_tokens: number
      average_daily_tokens: number
      cache_hit_rate_percent: number
      peak_day: string | null
      peak_day_tokens: number
    }
    top_models: {
      model: string
      tokens: number
      share_percent: number
    }[]
  } | null
  isLoading: boolean
  error: string | null
}

type SnapshotData = NonNullable<HookState['snapshot']>

const {
  initializeMock,
  projectStoreState,
  hookStateRef,
} = vi.hoisted(() => {
  const initializeMock = vi.fn(async () => undefined)
  const projectStoreState = {
    initialize: initializeMock,
    hasInitialized: true,
    isInitializing: false,
  }
  const hookStateRef: { current: HookState } = {
    current: {
      snapshot: null,
      isLoading: true,
      error: null,
    },
  }
  return {
    initializeMock,
    projectStoreState,
    hookStateRef,
  }
})

vi.mock('../../src/features/graph/Sidebar', () => ({
  Sidebar: () => <aside data-testid="sidebar-stub" />,
}))

vi.mock('../../src/stores/project-store', () => ({
  useProjectStore: (selector: (state: typeof projectStoreState) => unknown) => selector(projectStoreState),
}))

vi.mock('../../src/features/usage-snapshot/useLocalUsageSnapshot', () => ({
  useLocalUsageSnapshot: () => hookStateRef.current,
}))

import { UsageSnapshotPage } from '../../src/features/usage-snapshot/UsageSnapshotPage'

function makeSnapshot(overrides: Partial<SnapshotData> = {}): SnapshotData {
  return {
    updated_at: 1_710_000_000_000,
    days: [
      {
        day: '2026-04-01',
        input_tokens: 10,
        cached_input_tokens: 2,
        output_tokens: 5,
        total_tokens: 15,
        agent_time_ms: 1200,
        agent_runs: 1,
      },
      {
        day: '2026-04-02',
        input_tokens: 12,
        cached_input_tokens: 3,
        output_tokens: 6,
        total_tokens: 18,
        agent_time_ms: 1800,
        agent_runs: 2,
      },
      {
        day: '2026-04-03',
        input_tokens: 9,
        cached_input_tokens: 1,
        output_tokens: 4,
        total_tokens: 13,
        agent_time_ms: 600,
        agent_runs: 1,
      },
      {
        day: '2026-04-04',
        input_tokens: 15,
        cached_input_tokens: 4,
        output_tokens: 7,
        total_tokens: 22,
        agent_time_ms: 2400,
        agent_runs: 2,
      },
      {
        day: '2026-04-05',
        input_tokens: 8,
        cached_input_tokens: 2,
        output_tokens: 5,
        total_tokens: 13,
        agent_time_ms: 900,
        agent_runs: 1,
      },
      {
        day: '2026-04-06',
        input_tokens: 11,
        cached_input_tokens: 2,
        output_tokens: 8,
        total_tokens: 19,
        agent_time_ms: 1400,
        agent_runs: 2,
      },
      {
        day: '2026-04-07',
        input_tokens: 13,
        cached_input_tokens: 3,
        output_tokens: 9,
        total_tokens: 22,
        agent_time_ms: 2100,
        agent_runs: 3,
      },
    ],
    totals: {
      last7_days_tokens: 122,
      last30_days_tokens: 122,
      average_daily_tokens: 17,
      cache_hit_rate_percent: 21.3,
      peak_day: '2026-04-04',
      peak_day_tokens: 22,
    },
    top_models: [
      {
        model: 'gpt-5',
        tokens: 90,
        share_percent: 73.8,
      },
      {
        model: 'gpt-4.1',
        tokens: 32,
        share_percent: 26.2,
      },
    ],
    ...overrides,
  }
}

describe('UsageSnapshotPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    projectStoreState.hasInitialized = true
    projectStoreState.isInitializing = false
    hookStateRef.current = {
      snapshot: null,
      isLoading: true,
      error: null,
    }
  })

  it('renders loading skeleton on first load', () => {
    render(<UsageSnapshotPage />)

    expect(screen.getByTestId('usage-snapshot-loading')).toBeInTheDocument()
    expect(screen.getByTestId('sidebar-stub')).toBeInTheDocument()
  })

  it('renders blocking error state without manual retry controls', () => {
    hookStateRef.current = {
      snapshot: null,
      isLoading: false,
      error: 'request failed',
    }

    render(<UsageSnapshotPage />)

    expect(screen.getByTestId('usage-snapshot-error-blocking')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Retry' })).not.toBeInTheDocument()
  })

  it('renders empty state when snapshot has zero usage', () => {
    const emptySnapshot = makeSnapshot({
      days: [
        {
          day: '2026-04-07',
          input_tokens: 0,
          cached_input_tokens: 0,
          output_tokens: 0,
          total_tokens: 0,
          agent_time_ms: 0,
          agent_runs: 0,
        },
      ],
      totals: {
        last7_days_tokens: 0,
        last30_days_tokens: 0,
        average_daily_tokens: 0,
        cache_hit_rate_percent: 0,
        peak_day: null,
        peak_day_tokens: 0,
      },
      top_models: [],
    })

    hookStateRef.current = {
      snapshot: emptySnapshot,
      isLoading: false,
      error: null,
    }

    render(<UsageSnapshotPage />)

    expect(screen.getByTestId('usage-snapshot-empty')).toBeInTheDocument()
  })

  it('renders populated content without lede or manual refresh controls', () => {
    const snapshot = makeSnapshot()
    hookStateRef.current = {
      snapshot,
      isLoading: false,
      error: null,
    }

    render(<UsageSnapshotPage />)

    expect(screen.getByTestId('usage-snapshot-content')).toBeInTheDocument()
    expect(screen.queryByText(/Local rollups across all Codex sessions on this machine/i)).not.toBeInTheDocument()
    expect(screen.queryByTestId('usage-refresh-button')).not.toBeInTheDocument()
    expect(screen.getByText('7-day token trend')).toBeInTheDocument()
    expect(screen.getByText('Top models')).toBeInTheDocument()
    expect(screen.getByText('gpt-5')).toBeInTheDocument()
  })

  it('renders non-blocking error banner when stale data exists', () => {
    const snapshot = makeSnapshot()
    hookStateRef.current = {
      snapshot,
      isLoading: false,
      error: 'temporary timeout',
    }

    render(<UsageSnapshotPage />)

    expect(screen.getByTestId('usage-snapshot-error-banner')).toBeInTheDocument()
    expect(screen.getByTestId('usage-snapshot-content')).toBeInTheDocument()
  })

  it('shows project bootstrap loader when project store is still initializing', () => {
    projectStoreState.hasInitialized = false
    projectStoreState.isInitializing = true

    render(<UsageSnapshotPage />)

    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })
})
