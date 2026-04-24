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

import type {
  SessionFacadeOptions,
  SessionFacadeV2,
} from '../../src/features/session_v2/facade/useSessionFacadeV2'
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
  options?: SessionFacadeOptions
}

function FacadeHarness({ onFacade, options }: HarnessProps) {
  const facade = useSessionFacadeV2(options)

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

  it('forwards threadCreationPolicy during auto bootstrap thread creation', async () => {
    const threadCreationPolicy = {
      modelProvider: 'custom-provider',
      baseInstructions: 'Use the workflow defaults.',
    }
    mockApi.listLoadedThreadsV2.mockResolvedValue({ data: [], nextCursor: null })
    mockApi.listThreadsV2.mockResolvedValue({ data: [], nextCursor: null })

    render(
      <FacadeHarness
        options={{
          bootstrapPolicy: {
            threadCreationPolicy,
          },
        }}
        onFacade={() => {
          // no-op
        }}
      />,
    )

    await waitFor(() => {
      expect(mockApi.startThreadV2).toHaveBeenCalledWith(threadCreationPolicy)
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

  it('polls pending requests as fallback when stream is disconnected and slows after connect', async () => {
    vi.useFakeTimers()

    let latestFacade: SessionFacadeV2 | null = null

    render(
      <FacadeHarness
        options={{
          bootstrapPolicy: {
            autoBootstrapOnMount: false,
          },
        }}
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
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(mockApi.listPendingRequestsV2.mock.calls.length).toBe(initialPollCount + 1)

    const source = mockApi.openThreadEventsStreamV2.mock.results[0]?.value as MockEventSource
    await act(async () => {
      source.onopen?.call(source as unknown as EventSource, new Event('open'))
      await Promise.resolve()
    })

    expect(useThreadSessionStore.getState().streamState.connectedByThread['thread-1']).toBe(true)

    const connectedPollCount = mockApi.listPendingRequestsV2.mock.calls.length

    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000)
    })
    expect(mockApi.listPendingRequestsV2.mock.calls.length).toBe(connectedPollCount)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(25000)
    })
    expect(mockApi.listPendingRequestsV2.mock.calls.length).toBe(connectedPollCount + 1)
  })

  it('routes request resolve/reject commands through explicit session actions', async () => {
    let latestFacade: SessionFacadeV2 | null = null

    render(
      <FacadeHarness
        options={{
          bootstrapPolicy: {
            autoBootstrapOnMount: false,
          },
        }}
        onFacade={(facade) => {
          latestFacade = facade
        }}
      />,
    )

    await waitFor(() => {
      expect(latestFacade).not.toBeNull()
    })

    await act(async () => {
      await latestFacade?.commands.resolveRequest(' request-1 ', { approved: true })
      await latestFacade?.commands.rejectRequest('request-2', 'denied')
    })

    expect(mockApi.resolvePendingRequestV2).toHaveBeenCalledWith(
      'request-1',
      expect.objectContaining({
        resolutionKey: expect.any(String),
        result: { approved: true },
      }),
    )
    expect(mockApi.rejectPendingRequestV2).toHaveBeenCalledWith(
      'request-2',
      expect.objectContaining({
        resolutionKey: expect.any(String),
        reason: 'denied',
      }),
    )
  })

  it('supports bootstrap policy without auto mount bootstrap/select/create', async () => {
    render(
      <FacadeHarness
        options={{
          bootstrapPolicy: {
            autoBootstrapOnMount: false,
            autoSelectInitialThread: false,
            autoCreateThreadWhenEmpty: false,
          },
        }}
        onFacade={() => {
          // no-op
        }}
      />,
    )

    await act(async () => {
      await Promise.resolve()
    })

    expect(mockApi.initializeSessionV2).not.toHaveBeenCalled()
    expect(useThreadSessionStore.getState().activeThreadId).toBeNull()
  })

  it('forwards threadCreationPolicy during manual bootstrap thread creation', async () => {
    let latestFacade: SessionFacadeV2 | null = null
    const threadCreationPolicy = {
      modelProvider: 'custom-provider',
      developerInstructions: 'Stay scoped.',
    }
    mockApi.listLoadedThreadsV2.mockResolvedValue({ data: [], nextCursor: null })
    mockApi.listThreadsV2.mockResolvedValue({ data: [], nextCursor: null })

    render(
      <FacadeHarness
        options={{
          bootstrapPolicy: { autoBootstrapOnMount: false },
        }}
        onFacade={(facade) => {
          latestFacade = facade
        }}
      />,
    )

    await waitFor(() => {
      expect(latestFacade).not.toBeNull()
    })

    await act(async () => {
      await latestFacade?.commands.bootstrap({ threadCreationPolicy })
    })

    expect(mockApi.startThreadV2).toHaveBeenCalledWith(threadCreationPolicy)
  })

  it('forwards createThread and submit policies', async () => {
    let latestFacade: SessionFacadeV2 | null = null
    const threadCreationPolicy = {
      modelProvider: 'custom-provider',
      ephemeral: true,
    }
    const turnExecutionPolicy = {
      approvalPolicy: 'never',
      sandboxPolicy: { type: 'dangerFullAccess' },
      effort: 'high',
    }

    render(
      <FacadeHarness
        options={{
          bootstrapPolicy: { autoBootstrapOnMount: false },
        }}
        onFacade={(facade) => {
          latestFacade = facade
        }}
      />,
    )

    await waitFor(() => {
      expect(latestFacade).not.toBeNull()
    })

    await act(async () => {
      await latestFacade?.commands.createThread(threadCreationPolicy)
    })

    expect(mockApi.startThreadV2).toHaveBeenCalledWith(threadCreationPolicy)

    act(() => {
      useThreadSessionStore.getState().setActiveThreadId('thread-new')
      useThreadSessionStore.getState().upsertThread(makeThread({ id: 'thread-new' }))
    })

    await act(async () => {
      await latestFacade?.commands.submit(
        {
          input: [{ type: 'text', text: 'run tests' }],
          text: 'run tests',
          requestedPolicy: {
            accessMode: 'default-permissions',
            model: null,
          },
        },
        turnExecutionPolicy,
      )
    })

    expect(mockApi.startTurnV2).toHaveBeenCalledWith(
      'thread-new',
      expect.objectContaining(turnExecutionPolicy),
    )
  })

  it('selectThread(null) clears active thread and stops stream/poll without clearing metadata', async () => {
    vi.useFakeTimers()
    let latestFacade: SessionFacadeV2 | null = null

    render(
      <FacadeHarness
        options={{
          bootstrapPolicy: { autoBootstrapOnMount: false },
        }}
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

    expect(mockApi.openThreadEventsStreamV2).toHaveBeenCalledTimes(1)
    expect(useThreadSessionStore.getState().activeThreadId).toBe('thread-1')

    await act(async () => {
      await latestFacade?.commands.selectThread(null)
      await Promise.resolve()
    })

    const pollCountAfterClear = mockApi.listPendingRequestsV2.mock.calls.length
    expect(useThreadSessionStore.getState().activeThreadId).toBeNull()
    expect(useThreadSessionStore.getState().threadOrder).toContain('thread-1')
    expect(useConnectionStore.getState().connection.phase).toBe('initialized')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })

    expect(mockApi.listPendingRequestsV2.mock.calls.length).toBe(pollCountAfterClear)
    expect(mockApi.openThreadEventsStreamV2.mock.calls.length).toBe(1)
  })

  it('drops stale selectThread hydration when selectThread(null) happens mid-flight', async () => {
    let latestFacade: SessionFacadeV2 | null = null
    const readDeferred = deferred<{ thread: SessionThread }>()
    const turnsDeferred = deferred<{ data: never[]; nextCursor: null }>()

    mockApi.readThreadV2.mockImplementation((threadId: string) => {
      if (threadId === 'thread-2') {
        return readDeferred.promise
      }
      return Promise.resolve({ thread: makeThread({ id: threadId }) })
    })
    mockApi.listThreadTurnsV2.mockImplementation((threadId: string) => {
      if (threadId === 'thread-2') {
        return turnsDeferred.promise
      }
      return Promise.resolve({ data: [], nextCursor: null })
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
        makeThread({ id: 'thread-1' }),
        makeThread({ id: 'thread-2' }),
      ])
      useThreadSessionStore.getState().setActiveThreadId('thread-1')
    })

    await act(async () => {
      const switching = latestFacade?.commands.selectThread('thread-2')
      const clearing = latestFacade?.commands.selectThread(null)
      await clearing

      readDeferred.resolve({ thread: makeThread({ id: 'thread-2' }) })
      await Promise.resolve()
      turnsDeferred.resolve({ data: [], nextCursor: null })
      await switching
    })

    expect(useThreadSessionStore.getState().activeThreadId).toBeNull()
  })

  it('filters activeRequest by active thread when pendingRequestScope=activeThread', async () => {
    let latestFacade: SessionFacadeV2 | null = null

    render(
      <FacadeHarness
        options={{
          bootstrapPolicy: { autoBootstrapOnMount: false },
          pendingRequestScope: 'activeThread',
        }}
        onFacade={(facade) => {
          latestFacade = facade
        }}
      />,
    )

    act(() => {
      useThreadSessionStore.getState().setActiveThreadId('thread-2')
      usePendingRequestsStore.getState().hydrateFromServer([
        {
          requestId: 'req-1',
          method: 'item/tool/requestUserInput',
          threadId: 'thread-1',
          turnId: 'turn-1',
          itemId: 'item-1',
          status: 'pending',
          createdAtMs: 1,
          submittedAtMs: null,
          resolvedAtMs: null,
          payload: {},
        },
        {
          requestId: 'req-2',
          method: 'item/tool/requestUserInput',
          threadId: 'thread-2',
          turnId: 'turn-2',
          itemId: 'item-2',
          status: 'pending',
          createdAtMs: 2,
          submittedAtMs: null,
          resolvedAtMs: null,
          payload: {},
        },
      ])
      usePendingRequestsStore.getState().setActiveRequest('req-1')
    })

    await waitFor(() => {
      expect(latestFacade?.state.activeRequest?.requestId).toBe('req-2')
    })
  })
})
