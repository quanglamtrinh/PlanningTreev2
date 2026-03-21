import { act } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getCodexSnapshot: vi.fn(),
  },
}))

vi.mock('../../src/api/client', () => ({
  api: {
    getCodexSnapshot: apiMock.getCodexSnapshot,
  },
  appendAuthToken: (url: string) => url,
}))

class MockEventSource {
  url: string
  listeners: Record<string, ((event: { data: string }) => void)[]> = {}
  onopen: (() => void) | null = null
  onerror: (() => void) | null = null

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }

  addEventListener(event: string, fn: (event: { data: string }) => void) {
    if (!this.listeners[event]) {
      this.listeners[event] = []
    }
    this.listeners[event].push(fn)
  }

  close() {
    MockEventSource.closedCount += 1
  }

  emit(event: string, data: unknown) {
    for (const listener of this.listeners[event] ?? []) {
      listener({ data: JSON.stringify(data) })
    }
  }

  open() {
    this.onopen?.()
  }

  static instances: MockEventSource[] = []
  static closedCount = 0

  static reset() {
    MockEventSource.instances = []
    MockEventSource.closedCount = 0
  }
}

vi.stubGlobal('EventSource', MockEventSource)

import { useCodexStore } from '../../src/stores/codex-store'
import type { CodexSnapshot } from '../../src/api/types'

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function makeSnapshot(overrides: Partial<CodexSnapshot> = {}): CodexSnapshot {
  return {
    account: {
      type: 'chatgpt',
      email: 'user@example.com',
      plan_type: 'plus',
      requires_openai_auth: true,
    },
    rate_limits: {
      primary: {
        used_percent: 8,
        window_duration_mins: 300,
        resets_at: 1_777_777_777,
      },
      secondary: {
        used_percent: 49,
        window_duration_mins: 10_080,
        resets_at: 1_778_888_888,
      },
      credits: null,
      plan_type: 'plus',
    },
    ...overrides,
  }
}

describe('codex-store', () => {
  beforeEach(() => {
    vi.useRealTimers()
    MockEventSource.reset()
    useCodexStore.getState().disconnect()
    useCodexStore.setState(useCodexStore.getInitialState())
    vi.clearAllMocks()
  })

  it('initializes with a snapshot fetch and opens the SSE stream', async () => {
    const snapshot = makeSnapshot()
    apiMock.getCodexSnapshot.mockResolvedValue(snapshot)

    await act(async () => {
      await useCodexStore.getState().initialize()
    })

    expect(apiMock.getCodexSnapshot).toHaveBeenCalledTimes(1)
    expect(useCodexStore.getState().snapshot).toEqual(snapshot)
    expect(useCodexStore.getState().hasInitialized).toBe(true)
    expect(MockEventSource.instances).toHaveLength(1)
    expect(MockEventSource.instances[0]?.url).toBe('/v1/codex/events')
  })

  it('applies live snapshot updates from the SSE stream', async () => {
    apiMock.getCodexSnapshot.mockResolvedValue(makeSnapshot())

    await act(async () => {
      await useCodexStore.getState().initialize()
    })

    const updated = makeSnapshot({
      rate_limits: {
        primary: {
          used_percent: 12,
          window_duration_mins: 300,
          resets_at: 1_777_777_999,
        },
        secondary: null,
        credits: {
          has_credits: true,
          unlimited: false,
          balance: '3',
        },
        plan_type: 'plus',
      },
    })

    act(() => {
      MockEventSource.instances[0]?.open()
      MockEventSource.instances[0]?.emit('snapshot_updated', updated)
    })

    expect(useCodexStore.getState().snapshot).toEqual(updated)
    expect(useCodexStore.getState().connectionState).toBe('live')
  })

  it('recovers after stream errors by refetching and reopening the stream', async () => {
    vi.useFakeTimers()
    const initial = makeSnapshot()
    const recovered = makeSnapshot({
      rate_limits: {
        primary: {
          used_percent: 18,
          window_duration_mins: 300,
          resets_at: 1_777_778_555,
        },
        secondary: null,
        credits: null,
        plan_type: 'plus',
      },
    })
    apiMock.getCodexSnapshot
      .mockResolvedValueOnce(initial)
      .mockResolvedValueOnce(recovered)

    await act(async () => {
      await useCodexStore.getState().initialize()
    })

    await act(async () => {
      MockEventSource.instances[0]?.onerror?.()
      await Promise.resolve()
    })

    await act(async () => {
      vi.advanceTimersByTime(1000)
      await Promise.resolve()
    })

    expect(apiMock.getCodexSnapshot).toHaveBeenCalledTimes(2)
    expect(useCodexStore.getState().snapshot).toEqual(recovered)
    expect(MockEventSource.instances).toHaveLength(2)
  })

  it('ignores stale reconnect work after disconnect', async () => {
    vi.useFakeTimers()
    const reconnectFetch = deferred<CodexSnapshot>()
    apiMock.getCodexSnapshot
      .mockResolvedValueOnce(makeSnapshot())
      .mockReturnValueOnce(reconnectFetch.promise)

    await act(async () => {
      await useCodexStore.getState().initialize()
    })

    act(() => {
      MockEventSource.instances[0]?.onerror?.()
      useCodexStore.getState().disconnect()
    })

    await act(async () => {
      reconnectFetch.resolve(makeSnapshot({
        rate_limits: {
          primary: {
            used_percent: 99,
            window_duration_mins: 300,
            resets_at: 1_777_778_999,
          },
          secondary: null,
          credits: null,
          plan_type: 'plus',
        },
      }))
      await Promise.resolve()
    })

    act(() => {
      vi.runOnlyPendingTimers()
    })

    expect(useCodexStore.getState().connectionState).toBe('idle')
    expect(MockEventSource.instances).toHaveLength(1)
  })
})
