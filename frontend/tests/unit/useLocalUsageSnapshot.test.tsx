import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getLocalUsageSnapshot: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: {
    getLocalUsageSnapshot: apiMock.getLocalUsageSnapshot,
  },
}))

import type { LocalUsageSnapshot } from '../../src/api/types'
import {
  LOCAL_USAGE_POLL_INTERVAL_MS,
  useLocalUsageSnapshot,
} from '../../src/features/usage-snapshot/useLocalUsageSnapshot'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function makeSnapshot(updatedAt: number): LocalUsageSnapshot {
  return {
    updated_at: updatedAt,
    days: [
      {
        day: '2026-04-06',
        input_tokens: 10,
        cached_input_tokens: 2,
        output_tokens: 5,
        total_tokens: 15,
        agent_time_ms: 1200,
        agent_runs: 1,
      },
    ],
    totals: {
      last7_days_tokens: 15,
      last30_days_tokens: 15,
      average_daily_tokens: 2,
      cache_hit_rate_percent: 20,
      peak_day: '2026-04-06',
      peak_day_tokens: 15,
    },
    top_models: [
      {
        model: 'gpt-5',
        tokens: 15,
        share_percent: 100,
      },
    ],
  }
}

function HookHarness() {
  const {
    snapshot,
    isLoading,
    isRefreshing,
    error,
    lastSuccessfulAt,
    refresh,
  } = useLocalUsageSnapshot()

  return (
    <div>
      <div data-testid="loading">{String(isLoading)}</div>
      <div data-testid="refreshing">{String(isRefreshing)}</div>
      <div data-testid="error">{error ?? ''}</div>
      <div data-testid="updated">{snapshot?.updated_at ?? 'none'}</div>
      <div data-testid="last-successful">{lastSuccessfulAt ?? 'none'}</div>
      <button type="button" onClick={() => void refresh()}>
        Refresh
      </button>
    </div>
  )
}

describe('useLocalUsageSnapshot', () => {
  beforeEach(() => {
    vi.useRealTimers()
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('loads snapshot on mount', async () => {
    apiMock.getLocalUsageSnapshot.mockResolvedValue(makeSnapshot(1_710_000_000_000))

    render(<HookHarness />)

    expect(screen.getByTestId('loading')).toHaveTextContent('true')
    await waitFor(() => {
      expect(screen.getByTestId('updated')).toHaveTextContent('1710000000000')
    })
    expect(screen.getByTestId('error')).toHaveTextContent('')
    expect(screen.getByTestId('loading')).toHaveTextContent('false')
    expect(screen.getByTestId('refreshing')).toHaveTextContent('false')
    expect(screen.getByTestId('last-successful')).toHaveTextContent('1710000000000')
  })

  it('polls every 5 minutes after initial load', async () => {
    const setIntervalSpy = vi.spyOn(window, 'setInterval')
    apiMock.getLocalUsageSnapshot
      .mockResolvedValueOnce(makeSnapshot(1_710_000_000_000))
      .mockResolvedValueOnce(makeSnapshot(1_710_000_500_000))

    render(<HookHarness />)

    await waitFor(() => {
      expect(screen.getByTestId('updated')).toHaveTextContent('1710000000000')
    })

    await act(async () => {
      const pollTick = setIntervalSpy.mock.calls[0]?.[0] as (() => void) | undefined
      expect(setIntervalSpy).toHaveBeenCalledWith(expect.any(Function), LOCAL_USAGE_POLL_INTERVAL_MS)
      pollTick?.()
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(screen.getByTestId('updated')).toHaveTextContent('1710000500000')
    })
    expect(apiMock.getLocalUsageSnapshot).toHaveBeenCalledTimes(2)
  })

  it('supports manual refresh with refreshing state after initial snapshot', async () => {
    const manualRefresh = deferred<LocalUsageSnapshot>()
    apiMock.getLocalUsageSnapshot
      .mockResolvedValueOnce(makeSnapshot(1_710_000_000_000))
      .mockImplementationOnce(() => manualRefresh.promise)

    render(<HookHarness />)

    await waitFor(() => {
      expect(screen.getByTestId('updated')).toHaveTextContent('1710000000000')
    })

    fireEvent.click(screen.getByRole('button', { name: 'Refresh' }))
    expect(screen.getByTestId('refreshing')).toHaveTextContent('true')

    await act(async () => {
      manualRefresh.resolve(makeSnapshot(1_710_000_900_000))
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(screen.getByTestId('updated')).toHaveTextContent('1710000900000')
    })
    expect(screen.getByTestId('refreshing')).toHaveTextContent('false')
    expect(screen.getByTestId('last-successful')).toHaveTextContent('1710000900000')
  })

  it('ignores stale responses when a newer poll request resolves first', async () => {
    const setIntervalSpy = vi.spyOn(window, 'setInterval')
    const first = deferred<LocalUsageSnapshot>()
    const second = deferred<LocalUsageSnapshot>()

    apiMock.getLocalUsageSnapshot
      .mockImplementationOnce(() => first.promise)
      .mockImplementationOnce(() => second.promise)

    render(<HookHarness />)

    await act(async () => {
      const pollTick = setIntervalSpy.mock.calls[0]?.[0] as (() => void) | undefined
      pollTick?.()
      await Promise.resolve()
    })

    await act(async () => {
      second.resolve(makeSnapshot(2_000))
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(screen.getByTestId('updated')).toHaveTextContent('2000')
    })

    await act(async () => {
      first.resolve(makeSnapshot(1_000))
      await Promise.resolve()
    })

    expect(screen.getByTestId('updated')).toHaveTextContent('2000')
  })

  it('keeps existing snapshot visible when a poll update fails', async () => {
    const setIntervalSpy = vi.spyOn(window, 'setInterval')
    apiMock.getLocalUsageSnapshot
      .mockResolvedValueOnce(makeSnapshot(1_000))
      .mockRejectedValueOnce(new Error('poll timeout'))

    render(<HookHarness />)

    await waitFor(() => {
      expect(screen.getByTestId('updated')).toHaveTextContent('1000')
    })

    await act(async () => {
      const pollTick = setIntervalSpy.mock.calls[0]?.[0] as (() => void) | undefined
      pollTick?.()
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(screen.getByTestId('error')).toHaveTextContent('poll timeout')
    })
    expect(screen.getByTestId('updated')).toHaveTextContent('1000')
  })

  it('cleans up polling interval on unmount', async () => {
    const setIntervalSpy = vi.spyOn(window, 'setInterval')
    const clearIntervalSpy = vi.spyOn(window, 'clearInterval')
    apiMock.getLocalUsageSnapshot.mockResolvedValue(makeSnapshot(1_000))

    const { unmount } = render(<HookHarness />)

    await waitFor(() => {
      expect(apiMock.getLocalUsageSnapshot).toHaveBeenCalledTimes(1)
    })

    unmount()

    const intervalId = setIntervalSpy.mock.results[0]?.value
    expect(clearIntervalSpy).toHaveBeenCalledWith(intervalId)
  })
})
