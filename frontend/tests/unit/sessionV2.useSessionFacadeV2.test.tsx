import { act, render, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockApi = vi.hoisted(() => ({
  initializeSessionV2: vi.fn(),
  listLoadedThreadsV2: vi.fn(),
  listThreadsV2: vi.fn(),
  startThreadV2: vi.fn(),
  readThreadV2: vi.fn(),
  listThreadTurnsV2: vi.fn(),
  resumeThreadV2: vi.fn(),
  listModelsV2: vi.fn(),
  listPendingRequestsV2: vi.fn(),
  forkThreadV2: vi.fn(),
  startTurnV2: vi.fn(),
  steerTurnV2: vi.fn(),
  interruptTurnV2: vi.fn(),
  resolvePendingRequestV2: vi.fn(),
  rejectPendingRequestV2: vi.fn(),
  openThreadEventsStreamV2: vi.fn(),
}))

vi.mock('../../src/features/session_v2/api/client', () => ({
  initializeSessionV2: mockApi.initializeSessionV2,
  listLoadedThreadsV2: mockApi.listLoadedThreadsV2,
  listThreadsV2: mockApi.listThreadsV2,
  startThreadV2: mockApi.startThreadV2,
  readThreadV2: mockApi.readThreadV2,
  listThreadTurnsV2: mockApi.listThreadTurnsV2,
  resumeThreadV2: mockApi.resumeThreadV2,
  listModelsV2: mockApi.listModelsV2,
  listPendingRequestsV2: mockApi.listPendingRequestsV2,
  forkThreadV2: mockApi.forkThreadV2,
  startTurnV2: mockApi.startTurnV2,
  steerTurnV2: mockApi.steerTurnV2,
  interruptTurnV2: mockApi.interruptTurnV2,
  resolvePendingRequestV2: mockApi.resolvePendingRequestV2,
  rejectPendingRequestV2: mockApi.rejectPendingRequestV2,
  openThreadEventsStreamV2: mockApi.openThreadEventsStreamV2,
}))

import type { SessionFacadeV2 } from '../../src/features/session_v2/facade/useSessionFacadeV2'
import {
  getSessionFacadeRuntimeOwnershipSnapshot,
  resetSessionFacadeRuntimeOwnershipForTests,
  useSessionFacadeV2,
} from '../../src/features/session_v2/facade/useSessionFacadeV2'
import type { SessionThread } from '../../src/features/session_v2/contracts'
import { useConnectionStore } from '../../src/features/session_v2/store/connectionStore'
import { usePendingRequestsStore } from '../../src/features/session_v2/store/pendingRequestsStore'
import { useThreadSessionStore } from '../../src/features/session_v2/store/threadSessionStore'

class MockEventSource {
  onopen: ((this: EventSource, event: Event) => unknown) | null = null
  onerror: ((this: EventSource, event: Event) => unknown) | null = null

  addEventListener(): void {
    // no-op for hook tests
  }

  close(): void {
    // no-op for hook tests
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function makeThread(overrides: Partial<SessionThread> & { id: string }): SessionThread {
  return {
    id: overrides.id,
    name: overrides.name ?? null,
    modelProvider: overrides.modelProvider ?? 'openai',
    cwd: overrides.cwd ?? 'C:/repo',
    ephemeral: overrides.ephemeral ?? false,
    archived: overrides.archived ?? false,
    status: overrides.status ?? { type: 'idle' },
    createdAt: overrides.createdAt ?? 1,
    updatedAt: overrides.updatedAt ?? 1,
    turns: overrides.turns ?? [],
    model: overrides.model ?? null,
  }
}

type HarnessProps = {
  onFacade: (facade: SessionFacadeV2) => void
}

function FacadeHarness({ onFacade }: HarnessProps) {
  const facade = useSessionFacadeV2()

  useEffect(() => {
    onFacade(facade)
  }, [facade, onFacade])

  return null
}

function configureApiMocks(): void {
  mockApi.initializeSessionV2.mockResolvedValue({
    connection: {
      phase: 'initialized',
      clientName: 'PlanningTree Session V2',
      serverVersion: '1.0.0',
    },
  })
  mockApi.listLoadedThreadsV2.mockResolvedValue({ data: ['thread-1'], nextCursor: null })
  mockApi.listThreadsV2.mockResolvedValue({ data: [makeThread({ id: 'thread-1' })], nextCursor: null })
  mockApi.startThreadV2.mockResolvedValue({ thread: makeThread({ id: 'thread-new' }) })
  mockApi.readThreadV2.mockImplementation(async (threadId: string) => ({ thread: makeThread({ id: threadId }) }))
  mockApi.listThreadTurnsV2.mockResolvedValue({ data: [], nextCursor: null })
  mockApi.resumeThreadV2.mockImplementation(async (threadId: string) => ({ thread: makeThread({ id: threadId }) }))
  mockApi.listModelsV2.mockResolvedValue({ data: [], nextCursor: null })
  mockApi.listPendingRequestsV2.mockResolvedValue({ data: [] })
  mockApi.forkThreadV2.mockImplementation(async (threadId: string) => ({ thread: makeThread({ id: `${threadId}-fork` }) }))
  mockApi.startTurnV2.mockResolvedValue({
    turn: {
      id: 'turn-1',
      threadId: 'thread-1',
      status: 'inProgress',
      lastCodexStatus: 'inProgress',
      startedAtMs: 1,
      completedAtMs: null,
      items: [],
      error: null,
    },
  })
  mockApi.steerTurnV2.mockResolvedValue({
    turn: {
      id: 'turn-1',
      threadId: 'thread-1',
      status: 'inProgress',
      lastCodexStatus: 'inProgress',
      startedAtMs: 1,
      completedAtMs: null,
      items: [],
      error: null,
    },
  })
  mockApi.interruptTurnV2.mockResolvedValue({ status: 'ok' })
  mockApi.resolvePendingRequestV2.mockResolvedValue({ status: 'ok' })
  mockApi.rejectPendingRequestV2.mockResolvedValue({ status: 'ok' })
  mockApi.openThreadEventsStreamV2.mockImplementation(() => new MockEventSource() as unknown as EventSource)
}

describe('useSessionFacadeV2', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    resetSessionFacadeRuntimeOwnershipForTests()
    configureApiMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('auto bootstraps on mount', async () => {
    let latestFacade: SessionFacadeV2 | null = null

    render(
      <FacadeHarness
        onFacade={(facade) => {
          latestFacade = facade
        }}
      />,
    )

    await waitFor(() => {
      expect(mockApi.initializeSessionV2).toHaveBeenCalledTimes(1)
    })

    await waitFor(() => {
      expect(latestFacade?.state.activeThreadId).toBe('thread-1')
      expect(latestFacade?.state.connection.phase).toBe('initialized')
    })
  })

  it('keeps stores alive until last owner releases and then clears on final unmount', async () => {
    let facadeA: SessionFacadeV2 | null = null
    let facadeB: SessionFacadeV2 | null = null

    function MultiHarness({ showA, showB }: { showA: boolean; showB: boolean }) {
      return (
        <>
          {showA ? (
            <FacadeHarness
              onFacade={(facade) => {
                facadeA = facade
              }}
            />
          ) : null}
          {showB ? (
            <FacadeHarness
              onFacade={(facade) => {
                facadeB = facade
              }}
            />
          ) : null}
        </>
      )
    }

    const view = render(<MultiHarness showA showB />)

    await waitFor(() => {
      expect(getSessionFacadeRuntimeOwnershipSnapshot().ownerCount).toBe(2)
    })

    act(() => {
      useThreadSessionStore.getState().setThreadList([makeThread({ id: 'thread-persist' })])
    })

    view.rerender(<MultiHarness showA={false} showB />)

    expect(getSessionFacadeRuntimeOwnershipSnapshot().ownerCount).toBe(1)
    expect(useThreadSessionStore.getState().threadOrder).toContain('thread-persist')

    view.rerender(<MultiHarness showA={false} showB={false} />)

    expect(getSessionFacadeRuntimeOwnershipSnapshot().ownerCount).toBe(0)
    expect(useThreadSessionStore.getState().threadOrder).toEqual([])
    expect(usePendingRequestsStore.getState().queue).toEqual([])
    expect(useConnectionStore.getState().connection.phase).toBe('disconnected')
    expect(facadeA).not.toBeNull()
    expect(facadeB).not.toBeNull()
  })

  it('drops stale selectThread async results when user switches quickly', async () => {
    let latestFacade: SessionFacadeV2 | null = null

    const readDeferredByThread: Record<string, ReturnType<typeof deferred<{ thread: SessionThread }>>> = {}
    const turnsDeferredByThread: Record<string, ReturnType<typeof deferred<{ data: never[]; nextCursor: null }>>> = {}

    mockApi.readThreadV2.mockImplementation((threadId: string) => {
      const def = deferred<{ thread: SessionThread }>()
      readDeferredByThread[threadId] = def
      return def.promise
    })
    mockApi.listThreadTurnsV2.mockImplementation((threadId: string) => {
      const def = deferred<{ data: never[]; nextCursor: null }>()
      turnsDeferredByThread[threadId] = def
      return def.promise
    })

    render(
      <FacadeHarness
        onFacade={(facade) => {
          latestFacade = facade
        }}
      />,
    )

    await waitFor(() => {
      expect(mockApi.initializeSessionV2).toHaveBeenCalled()
    })

    act(() => {
      useThreadSessionStore.getState().setThreadList([
        makeThread({ id: 'thread-0' }),
        makeThread({ id: 'thread-1' }),
        makeThread({ id: 'thread-2' }),
      ])
      useThreadSessionStore.getState().setActiveThreadId('thread-0')
    })

    await act(async () => {
      const first = latestFacade?.commands.selectThread('thread-1')
      const second = latestFacade?.commands.selectThread('thread-2')

      readDeferredByThread['thread-1'].resolve({ thread: makeThread({ id: 'thread-1' }) })
      await Promise.resolve()
      turnsDeferredByThread['thread-1']?.resolve({ data: [], nextCursor: null })
      await first

      readDeferredByThread['thread-2'].resolve({ thread: makeThread({ id: 'thread-2' }) })
      await Promise.resolve()
      turnsDeferredByThread['thread-2'].resolve({ data: [], nextCursor: null })
      await second
    })

    expect(useThreadSessionStore.getState().activeThreadId).toBe('thread-2')
  })

  it('cleans up stores on unmount for single owner lifecycle', async () => {
    const view = render(
      <FacadeHarness
        onFacade={() => {
          // no-op
        }}
      />,
    )

    await waitFor(() => {
      expect(mockApi.initializeSessionV2).toHaveBeenCalled()
    })

    view.unmount()

    expect(getSessionFacadeRuntimeOwnershipSnapshot().ownerCount).toBe(0)
    expect(useThreadSessionStore.getState().threadOrder).toEqual([])
    expect(usePendingRequestsStore.getState().queue).toEqual([])
    expect(useConnectionStore.getState().connection.phase).toBe('disconnected')
  })

  it('polls pending requests at 2000ms idle and 400ms while turn is running', async () => {
    vi.useFakeTimers()

    let latestFacade: SessionFacadeV2 | null = null

    render(
      <FacadeHarness
        onFacade={(facade) => {
          latestFacade = facade
        }}
      />,
    )

    await act(async () => {
      await latestFacade?.commands.bootstrap()
      await Promise.resolve()
      await Promise.resolve()
    })

    const initialPollCount = mockApi.listPendingRequestsV2.mock.calls.length
    expect(initialPollCount).toBeGreaterThan(0)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1999)
    })
    expect(mockApi.listPendingRequestsV2.mock.calls.length).toBe(initialPollCount)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    const afterIdlePollCount = mockApi.listPendingRequestsV2.mock.calls.length
    expect(afterIdlePollCount).toBeGreaterThanOrEqual(initialPollCount + 1)

    act(() => {
      useThreadSessionStore.getState().setThreadTurns('thread-1', [
        {
          id: 'turn-running',
          threadId: 'thread-1',
          status: 'inProgress',
          lastCodexStatus: 'inProgress',
          startedAtMs: 1,
          completedAtMs: null,
          items: [],
          error: null,
        },
      ])
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    expect(mockApi.listPendingRequestsV2.mock.calls.length).toBeGreaterThanOrEqual(afterIdlePollCount + 1)
  })
})
