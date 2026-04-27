import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { PendingServerRequest, SessionThread, SessionTurn } from '../../src/features/session_v2/contracts'
import { createSessionRuntimeController } from '../../src/features/session_v2/facade/sessionRuntimeController'
import type { ThreadSessionStoreState } from '../../src/features/session_v2/store/threadSessionStore'

function makeThread(partial: Partial<SessionThread> & { id: string }): SessionThread {
  return {
    id: partial.id,
    name: partial.name ?? null,
    modelProvider: partial.modelProvider ?? 'openai',
    cwd: partial.cwd ?? 'C:/repo',
    ephemeral: partial.ephemeral ?? false,
    archived: partial.archived ?? false,
    status: partial.status ?? { type: 'idle' },
    createdAt: partial.createdAt ?? 1,
    updatedAt: partial.updatedAt ?? 1,
    turns: partial.turns ?? [],
    model: partial.model ?? null,
  }
}

function makeTurn(partial: Partial<SessionTurn> & { id: string; threadId: string }): SessionTurn {
  return {
    id: partial.id,
    threadId: partial.threadId,
    status: partial.status ?? 'inProgress',
    lastCodexStatus: partial.lastCodexStatus ?? 'inProgress',
    startedAtMs: partial.startedAtMs ?? 1,
    completedAtMs: partial.completedAtMs ?? null,
    items: partial.items ?? [],
    error: partial.error ?? null,
  }
}

type TestHarness = ReturnType<typeof createHarness>

function createHarness() {
  const threadState = {
    threadsById: {},
    threadOrder: [],
    turnsByThread: {},
    itemsByTurn: {},
    lastEventSeqByThread: {},
    lastEventIdByThread: {},
    gapDetectedByThread: {},
    threadStatus: {},
    tokenUsageByThread: {},
    activeThreadId: null,
    streamState: { connectedByThread: {}, reconnectCountByThread: {} },
  } as unknown as ThreadSessionStoreState

  const runtimeSnapshot = {
    activeThreadId: null,
    activeTurns: [] as SessionTurn[],
    activeRunningTurn: null as SessionTurn | null,
    selectedModel: null as string | null,
  }

  const setThreadList = vi.fn((rows: SessionThread[]) => {
    const nextById: Record<string, SessionThread> = { ...threadState.threadsById }
    for (const row of rows) {
      nextById[row.id] = row
    }
    threadState.threadsById = nextById
    threadState.threadOrder = rows.map((row) => row.id)
  })

  const upsertThread = vi.fn((thread: SessionThread) => {
    threadState.threadsById = {
      ...threadState.threadsById,
      [thread.id]: thread,
    }
    if (!threadState.threadOrder.includes(thread.id)) {
      threadState.threadOrder = [...threadState.threadOrder, thread.id]
    }
  })

  const setActiveThreadId = vi.fn((threadId: string | null) => {
    threadState.activeThreadId = threadId
  })

  const setThreadTurns = vi.fn((threadId: string, turns: SessionTurn[]) => {
    threadState.turnsByThread = {
      ...threadState.turnsByThread,
      [threadId]: turns,
    }
  })

  const setReplayCursor = vi.fn((threadId: string, lastEventSeq: number, lastEventId: string | null) => {
    if (lastEventSeq <= 0 && (lastEventId == null || String(lastEventId).trim() === '')) {
      const nextSeq = { ...threadState.lastEventSeqByThread } as Record<string, number>
      const nextId = { ...threadState.lastEventIdByThread } as Record<string, string>
      delete nextSeq[threadId]
      delete nextId[threadId]
      threadState.lastEventSeqByThread = nextSeq
      threadState.lastEventIdByThread = nextId
    } else {
      const seq = Math.max(0, lastEventSeq)
      threadState.lastEventSeqByThread = { ...threadState.lastEventSeqByThread, [threadId]: seq }
      const nextId = lastEventId != null && String(lastEventId).trim() !== '' ? String(lastEventId).trim() : `${threadId}:${seq}`
      threadState.lastEventIdByThread = { ...threadState.lastEventIdByThread, [threadId]: nextId }
    }
    threadState.gapDetectedByThread = { ...threadState.gapDetectedByThread, [threadId]: false }
  })

  const hydratePendingRequests = vi.fn()
  const markPendingRequestSubmitted = vi.fn()
  const setConnectionPhase = vi.fn()
  const setConnectionInitialized = vi.fn()
  const setConnectionError = vi.fn()
  const setRuntimeError = vi.fn()
  const setIsBootstrapping = vi.fn()
  const setIsModelLoading = vi.fn()
  const setModelOptions = vi.fn()
  const setLastPendingPollAtMs = vi.fn()
  const markThreadActivity = vi.fn()

  const api = {
    initializeSession: vi.fn(async () => ({
      connection: {
        phase: 'initialized',
        clientName: 'PlanningTree Session V2',
        serverVersion: '1.0.0',
      },
    })),
    listLoadedThreads: vi.fn(async () => ({ data: [], nextCursor: null })),
    listThreads: vi.fn(async () => ({ data: [], nextCursor: null })),
    startThread: vi.fn(async () => ({ thread: makeThread({ id: 'thread-new' }) })),
    readThread: vi.fn(async (threadId: string) => ({ thread: makeThread({ id: threadId }) })),
    listThreadTurns: vi.fn(async () => ({ data: [], nextCursor: null })),
    resumeThread: vi.fn(async (threadId: string) => ({ thread: makeThread({ id: threadId }) })),
    listModels: vi.fn(async () => ({ data: [], nextCursor: null })),
    listPendingRequests: vi.fn(async () => ({ data: [] })),
    steerTurn: vi.fn(async (threadId: string, turnId: string) => ({
      turn: makeTurn({ id: turnId, threadId, status: 'inProgress' }),
    })),
    startTurn: vi.fn(async (threadId: string) => ({
      turn: makeTurn({ id: 'turn-started', threadId, status: 'inProgress' }),
    })),
    interruptTurn: vi.fn(async () => ({ status: 'ok' })),
    resolvePendingRequest: vi.fn(async () => ({ status: 'ok' })),
    rejectPendingRequest: vi.fn(async () => ({ status: 'ok' })),
    forkThread: vi.fn(async (threadId: string) => ({
      thread: makeThread({ id: `${threadId}-fork` }),
    })),
    getThreadJournalHead: vi.fn(async (threadId: string) => ({
      threadId,
      firstEventSeq: null,
      lastEventSeq: null,
      lastEventId: null,
    })),
  }

  const controller = createSessionRuntimeController({
    getThreadState: () => threadState,
    getRuntimeSnapshot: () => runtimeSnapshot,
    setThreadList,
    setReplayCursor,
    upsertThread,
    markThreadActivity,
    setActiveThreadId,
    setThreadTurns,
    hydratePendingRequests,
    markPendingRequestSubmitted,
    setConnectionPhase,
    setConnectionInitialized,
    setConnectionError,
    setRuntimeError,
    setIsBootstrapping,
    setIsModelLoading,
    setModelOptions,
    setLastPendingPollAtMs,
    isDisposed: () => false,
    api,
  })

  return {
    controller,
    threadState,
    runtimeSnapshot,
    api,
    spies: {
      setThreadList,
      setReplayCursor,
      upsertThread,
      setActiveThreadId,
      setThreadTurns,
      hydratePendingRequests,
      markPendingRequestSubmitted,
      setConnectionPhase,
      setConnectionInitialized,
      setConnectionError,
      setRuntimeError,
      setIsBootstrapping,
      setIsModelLoading,
      setModelOptions,
      setLastPendingPollAtMs,
      markThreadActivity,
    },
  }
}

describe('sessionRuntimeController', () => {
  let harness: TestHarness

  beforeEach(() => {
    harness = createHarness()
  })

  it('bootstraps and falls back to create thread when list is empty', async () => {
    await harness.controller.bootstrap()

    expect(harness.api.initializeSession).toHaveBeenCalledTimes(1)
    expect(harness.api.listLoadedThreads).toHaveBeenCalledWith({ limit: 20 })
    expect(harness.api.listThreads).toHaveBeenCalledWith({ limit: 50 })
    expect(harness.api.startThread).toHaveBeenCalledWith({})
    expect(harness.threadState.activeThreadId).toBe('thread-new')
    expect(harness.spies.setConnectionInitialized).toHaveBeenCalledWith('PlanningTree Session V2', '1.0.0')
    expect(harness.spies.setIsBootstrapping).toHaveBeenNthCalledWith(1, true)
    expect(harness.spies.setIsBootstrapping).toHaveBeenLastCalledWith(false)
  })

  it('resumes thread when cached status is notLoaded before hydrate', async () => {
    harness.threadState.threadsById = {
      'thread-1': makeThread({ id: 'thread-1', status: { type: 'notLoaded' } }),
    }

    await harness.controller.ensureThreadReady('thread-1')

    expect(harness.api.resumeThread).toHaveBeenCalledWith('thread-1', {})
    expect(harness.api.readThread).toHaveBeenCalledWith('thread-1', true)
    expect(harness.api.listThreadTurns).not.toHaveBeenCalled()
    expect(harness.spies.setThreadTurns).toHaveBeenCalledWith('thread-1', [], { mode: 'replace' })
  })

  it('hydrates by replacing from thread/read turns without listing turns', async () => {
    const turn = makeTurn({
      id: 'turn-from-read',
      threadId: 'thread-1',
      status: 'completed',
      completedAtMs: 2,
    })
    harness.api.readThread.mockResolvedValue({
      thread: makeThread({ id: 'thread-1', turns: [turn] }),
    })

    await harness.controller.hydrateThreadState('thread-1', { force: true })

    expect(harness.api.readThread).toHaveBeenCalledWith('thread-1', true)
    expect(harness.api.listThreadTurns).not.toHaveBeenCalled()
    expect(harness.spies.setThreadTurns).toHaveBeenCalledWith('thread-1', [turn], { mode: 'replace' })
  })

  it('hydrates thread state with replace mode during full resync recovery', async () => {
    await harness.controller.hydrateThreadState('thread-1', {
      force: true,
      replaceProjection: true,
    })

    expect(harness.spies.setThreadTurns).toHaveBeenCalledWith('thread-1', [], { mode: 'replace' })
  })

  it('does not align the SSE replay cursor from journal head after provider snapshot hydrate', async () => {
    harness.api.getThreadJournalHead.mockResolvedValue({
      threadId: 'thread-1',
      firstEventSeq: 1,
      lastEventSeq: 42,
      lastEventId: 'thread-1:42',
    })
    await harness.controller.hydrateThreadState('thread-1', { force: true })
    expect(harness.api.getThreadJournalHead).not.toHaveBeenCalled()
    expect(harness.spies.setReplayCursor).not.toHaveBeenCalled()
  })

  it('reads provider snapshot without touching the independent SSE cursor', async () => {
    await harness.controller.hydrateThreadState('thread-1', { force: true })

    expect(harness.api.getThreadJournalHead).not.toHaveBeenCalled()
    expect(harness.api.readThread).toHaveBeenCalledWith('thread-1', true)
    expect(harness.spies.setReplayCursor).not.toHaveBeenCalled()
  })

  it('submits steer request when active turn is running', async () => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeTurns = [
      makeTurn({ id: 'turn-1', threadId: 'thread-1', status: 'inProgress' }),
    ]
    harness.runtimeSnapshot.activeRunningTurn =
      harness.runtimeSnapshot.activeTurns[0]

    await harness.controller.submit({
      input: [{ type: 'text', text: 'continue' }],
      text: 'continue',
      requestedPolicy: {
        accessMode: 'default-permissions',
        model: null,
      },
    })

    expect(harness.api.steerTurn).toHaveBeenCalledTimes(1)
    expect(harness.api.startTurn).not.toHaveBeenCalled()
    expect(harness.spies.markThreadActivity).toHaveBeenCalledWith('thread-1')
  })

  it('starts new turn with execution policy derived from composer access mode', async () => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeTurns = []
    harness.runtimeSnapshot.activeRunningTurn = null
    harness.runtimeSnapshot.selectedModel = 'gpt-5'

    await harness.controller.submit({
      input: [{ type: 'text', text: 'run tests' }],
      text: 'run tests',
      requestedPolicy: {
        accessMode: 'full-access',
        model: null,
      },
    })

    expect(harness.api.startTurn).toHaveBeenCalledTimes(1)
    const [, request] = harness.api.startTurn.mock.calls[0]
    expect(request.model).toBe('gpt-5')
    expect(request.approvalPolicy).toBe('never')
    expect(request.sandboxPolicy).toEqual({ type: 'dangerFullAccess' })
  })



  it('includes MCP context in turn/start without mixing it into execution policy', async () => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeTurns = []
    harness.runtimeSnapshot.activeRunningTurn = null
    harness.runtimeSnapshot.selectedModel = 'gpt-5'

    await harness.controller.submit(
      {
        input: [{ type: 'text', text: 'use mcp' }],
        text: 'use mcp',
        requestedPolicy: {
          accessMode: 'full-access',
          model: null,
        },
      },
      { effort: 'high' },
      { mcpContext: { projectId: 'project-1', nodeId: 'node-1', role: 'execution' } },
    )

    const [, request] = harness.api.startTurn.mock.calls[0]
    expect(request).toEqual(
      expect.objectContaining({
        input: [{ type: 'text', text: 'use mcp' }],
        model: 'gpt-5',
        effort: 'high',
        mcpContext: { projectId: 'project-1', nodeId: 'node-1', role: 'execution' },
      }),
    )
  })

  it('maps default Codex composer model and high effort into turn/start config', async () => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeTurns = []
    harness.runtimeSnapshot.activeRunningTurn = null
    harness.runtimeSnapshot.selectedModel = 'gpt-5.3-codex'

    await harness.controller.submit({
      input: [{ type: 'text', text: 'run with codex defaults' }],
      text: 'run with codex defaults',
      requestedPolicy: {
        accessMode: 'full-access',
        model: 'gpt-5.3-codex',
        effort: 'high',
      },
    })

    expect(harness.api.startTurn).toHaveBeenCalledTimes(1)
    const [, request] = harness.api.startTurn.mock.calls[0]
    expect(request).toEqual(
      expect.objectContaining({
        input: [{ type: 'text', text: 'run with codex defaults' }],
        model: 'gpt-5.3-codex',
        effort: 'high',
        approvalPolicy: 'never',
        sandboxPolicy: { type: 'dangerFullAccess' },
      }),
    )
  })

  it('defaults missing composer permissions to full access in turn/start config', async () => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeTurns = []
    harness.runtimeSnapshot.activeRunningTurn = null
    harness.runtimeSnapshot.selectedModel = 'gpt-5.3-codex'

    await harness.controller.submit({
      input: [{ type: 'text', text: 'run with implicit full permissions' }],
      text: 'run with implicit full permissions',
      requestedPolicy: {
        model: 'gpt-5.3-codex',
        effort: 'high',
      },
    })

    expect(harness.api.startTurn).toHaveBeenCalledTimes(1)
    const [, request] = harness.api.startTurn.mock.calls[0]
    expect(request).toEqual(
      expect.objectContaining({
        model: 'gpt-5.3-codex',
        effort: 'high',
        approvalPolicy: 'never',
        sandboxPolicy: { type: 'dangerFullAccess' },
      }),
    )
  })

  it('dispatches explicit turn start actions through the unified input pipeline', async () => {
    await harness.controller.submitSessionAction({
      type: 'turn.start',
      threadId: 'thread-1',
      input: [{ type: 'text', text: 'run tests' }],
      policy: {
        model: 'gpt-5.2',
        approvalPolicy: 'never',
        sandboxPolicy: { type: 'dangerFullAccess' },
      },
    })

    expect(harness.api.startTurn).toHaveBeenCalledWith(
      'thread-1',
      expect.objectContaining({
        input: [{ type: 'text', text: 'run tests' }],
        model: 'gpt-5.2',
        approvalPolicy: 'never',
        sandboxPolicy: { type: 'dangerFullAccess' },
      }),
    )
    expect(harness.spies.setThreadTurns).toHaveBeenCalledWith(
      'thread-1',
      [expect.objectContaining({ id: 'turn-started', threadId: 'thread-1' })],
    )
    expect(harness.spies.markThreadActivity).toHaveBeenCalledWith('thread-1')
  })

  it('dispatches explicit request resolution actions through the unified input pipeline', async () => {
    await harness.controller.submitSessionAction({
      type: 'request.resolve',
      requestId: 'request-1',
      result: { approved: true },
      resolutionKey: 'resolution-1',
    })

    expect(harness.api.resolvePendingRequest).toHaveBeenCalledWith(
      'request-1',
      {
        resolutionKey: 'resolution-1',
        result: { approved: true },
      },
    )
    expect(harness.spies.markPendingRequestSubmitted).toHaveBeenCalledWith('request-1')
  })

  it('dispatches explicit request rejection actions through the unified input pipeline', async () => {
    await harness.controller.submitSessionAction({
      type: 'request.reject',
      requestId: 'request-1',
      reason: 'denied',
      resolutionKey: 'resolution-2',
    })

    expect(harness.api.rejectPendingRequest).toHaveBeenCalledWith(
      'request-1',
      {
        resolutionKey: 'resolution-2',
        reason: 'denied',
      },
    )
    expect(harness.spies.markPendingRequestSubmitted).toHaveBeenCalledWith('request-1')
  })

  it('passes supplied turn execution policy through and gives policy model precedence', async () => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeTurns = []
    harness.runtimeSnapshot.activeRunningTurn = null
    harness.runtimeSnapshot.selectedModel = 'gpt-5'

    await harness.controller.submit(
      {
        input: [{ type: 'text', text: 'run tests' }],
        text: 'run tests',
        requestedPolicy: {
          accessMode: 'default-permissions',
          model: 'gpt-5.1',
        },
      },
      {
        model: 'gpt-5.2',
        approvalPolicy: 'never',
        sandboxPolicy: { type: 'dangerFullAccess' },
        effort: 'high',
      },
    )

    expect(harness.api.startTurn).toHaveBeenCalledTimes(1)
    const [, request] = harness.api.startTurn.mock.calls[0]
    expect(request).toEqual(
      expect.objectContaining({
        input: [{ type: 'text', text: 'run tests' }],
        model: 'gpt-5.2',
        approvalPolicy: 'never',
        sandboxPolicy: { type: 'dangerFullAccess' },
        effort: 'high',
      }),
    )
  })

  it.each([
    ['low', 'low'],
    ['medium', 'medium'],
    ['high', 'high'],
    ['extra-high', 'xhigh'],
  ] as const)('maps composer %s effort to Codex turn/start effort %s', async (composerEffort, codexEffort) => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeTurns = []
    harness.runtimeSnapshot.activeRunningTurn = null
    harness.runtimeSnapshot.selectedModel = 'gpt-5'

    await harness.controller.submit({
      input: [{ type: 'text', text: 'think with selected effort' }],
      text: 'think with selected effort',
      requestedPolicy: {
        accessMode: 'default-permissions',
        effort: composerEffort,
      },
    })

    const [, request] = harness.api.startTurn.mock.calls[0]
    expect(request.approvalPolicy).toBe('on-request')
    expect(request.sandboxPolicy).toEqual({ type: 'workspaceWrite' })
    expect(request.effort).toBe(codexEffort)
  })

  it.each([
    ['full-access', 'never', { type: 'dangerFullAccess' }],
    ['default-permissions', 'on-request', { type: 'workspaceWrite' }],
    ['read-only', 'on-request', { type: 'readOnly' }],
  ] as const)('maps composer %s permissions to Codex turn/start policy', async (
    accessMode,
    approvalPolicy,
    sandboxPolicy,
  ) => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeTurns = []
    harness.runtimeSnapshot.activeRunningTurn = null
    harness.runtimeSnapshot.selectedModel = 'gpt-5'

    await harness.controller.submit({
      input: [{ type: 'text', text: 'run with selected permissions' }],
      text: 'run with selected permissions',
      requestedPolicy: {
        accessMode,
      },
    })

    const [, request] = harness.api.startTurn.mock.calls[0]
    expect(request.approvalPolicy).toBe(approvalPolicy)
    expect(request.sandboxPolicy).toEqual(sandboxPolicy)
  })

  it('skips null, undefined, and blank model values before selected model fallback', async () => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeTurns = []
    harness.runtimeSnapshot.activeRunningTurn = null
    harness.runtimeSnapshot.selectedModel = 'gpt-5'

    await harness.controller.submit(
      {
        input: [{ type: 'text', text: 'run tests' }],
        text: 'run tests',
        requestedPolicy: {
          accessMode: 'default-permissions',
          model: '   ',
        },
      },
      {
        model: null,
      },
    )

    const [, nullPolicyModelRequest] = harness.api.startTurn.mock.calls[0]
    expect(nullPolicyModelRequest.model).toBe('gpt-5')

    harness.api.startTurn.mockClear()

    await harness.controller.submit({
      input: [{ type: 'text', text: 'run tests again' }],
      text: 'run tests again',
      requestedPolicy: {
        accessMode: 'default-permissions',
      },
    })

    const [, undefinedPolicyModelRequest] = harness.api.startTurn.mock.calls[0]
    expect(undefinedPolicyModelRequest.model).toBe('gpt-5')
  })

  it('creates thread without policy using backend defaults', async () => {
    await harness.controller.createThread()

    expect(harness.api.startThread).toHaveBeenCalledWith({})
  })

  it('passes createThread policy through unchanged', async () => {
    const policy = {
      model: 'gpt-5.2',
      modelProvider: 'custom',
      cwd: 'C:/repo',
      approvalPolicy: 'onRequest',
      sandbox: { type: 'workspaceWrite' },
      ephemeral: true,
    }

    await harness.controller.createThread(policy)

    expect(harness.api.startThread).toHaveBeenCalledWith(policy)
  })

  it('polls pending requests and updates poll timestamp', async () => {
    const pendingRow: PendingServerRequest = {
      requestId: 'request-1',
      method: 'item/tool/requestUserInput',
      threadId: 'thread-1',
      turnId: 'turn-1',
      itemId: 'item-1',
      status: 'pending',
      createdAtMs: 1,
      submittedAtMs: null,
      resolvedAtMs: null,
      payload: {},
    }
    harness.api.listPendingRequests.mockResolvedValue({ data: [pendingRow] })

    await harness.controller.pollPendingRequests()

    expect(harness.spies.hydratePendingRequests).toHaveBeenCalledWith([pendingRow])
    expect(harness.spies.setLastPendingPollAtMs).toHaveBeenCalledTimes(1)
  })

  it('selectThread re-fetches from server when cache says hydrated but transcript is empty in store', async () => {
    const turn = makeTurn({
      id: 'turn-from-read',
      threadId: 'thread-1',
      status: 'completed',
      completedAtMs: 2,
    })
    harness.api.readThread.mockResolvedValue({
      thread: makeThread({ id: 'thread-1', turns: [turn] }),
    })
    harness.threadState.threadsById = {
      'thread-1': makeThread({ id: 'thread-1', status: { type: 'idle' } }),
    }
    await harness.controller.selectThread('thread-1')
    expect(harness.api.readThread).toHaveBeenCalledTimes(1)
    expect((harness.threadState.turnsByThread as Record<string, SessionTurn[]>)['thread-1']).toEqual([turn])
    harness.api.readThread.mockClear()

    harness.threadState.turnsByThread = { 'thread-1': [] } as unknown as typeof harness.threadState.turnsByThread

    await harness.controller.selectThread('thread-1')
    expect(harness.api.readThread).toHaveBeenCalledWith('thread-1', true)
  })

  it('selectThread skips re-read from server when transcript is still present in store', async () => {
    const turn = makeTurn({
      id: 'turn-from-read',
      threadId: 'thread-1',
      status: 'completed',
      completedAtMs: 2,
    })
    harness.api.readThread.mockResolvedValue({
      thread: makeThread({ id: 'thread-1', turns: [turn] }),
    })
    harness.threadState.threadsById = {
      'thread-1': makeThread({ id: 'thread-1', status: { type: 'idle' } }),
    }
    await harness.controller.selectThread('thread-1')
    expect(harness.api.readThread).toHaveBeenCalledTimes(1)
    harness.api.readThread.mockClear()

    await harness.controller.selectThread('thread-1')
    expect(harness.api.readThread).not.toHaveBeenCalled()
  })

  it('selectThread(null) clears active selection without clearing metadata', async () => {
    harness.threadState.activeThreadId = 'thread-1'
    harness.threadState.threadsById = {
      'thread-1': makeThread({ id: 'thread-1' }),
    }
    harness.threadState.threadOrder = ['thread-1']

    await harness.controller.selectThread(null)

    expect(harness.spies.setActiveThreadId).toHaveBeenCalledWith(null)
    expect(harness.threadState.threadOrder).toEqual(['thread-1'])
    expect(harness.api.readThread).not.toHaveBeenCalled()
    expect(harness.api.listThreadTurns).not.toHaveBeenCalled()
    expect(harness.api.resumeThread).not.toHaveBeenCalled()
  })

  it('bootstrap keeps metadata but skips auto-select/create when policy disables it', async () => {
    harness.api.listLoadedThreads.mockResolvedValue({ data: ['thread-1'], nextCursor: null })
    harness.api.listThreads.mockResolvedValue({
      data: [makeThread({ id: 'thread-1' }), makeThread({ id: 'thread-2' })],
      nextCursor: null,
    })

    await harness.controller.bootstrap({
      autoSelectInitialThread: false,
      autoCreateThreadWhenEmpty: false,
    })

    expect(harness.spies.setThreadList).toHaveBeenCalledWith([
      makeThread({ id: 'thread-1' }),
      makeThread({ id: 'thread-2' }),
    ])
    expect(harness.threadState.threadOrder).toEqual(['thread-1', 'thread-2'])
    expect(harness.spies.setActiveThreadId).not.toHaveBeenCalledWith('thread-1')
    expect(harness.api.startThread).not.toHaveBeenCalled()
  })

  it('passes bootstrap threadCreationPolicy through when auto-creating a thread', async () => {
    const threadCreationPolicy = {
      modelProvider: 'custom-provider',
      approvalsReviewer: 'reviewer-1',
      developerInstructions: 'Stay within the task boundary.',
      config: { profile: 'execution' },
    }

    await harness.controller.bootstrap({
      autoSelectInitialThread: true,
      autoCreateThreadWhenEmpty: true,
      threadCreationPolicy,
    })

    expect(harness.api.startThread).toHaveBeenCalledWith(threadCreationPolicy)
  })

  it('interrupts running turn through the unified input pipeline', async () => {
    harness.runtimeSnapshot.activeThreadId = 'thread-1'
    harness.runtimeSnapshot.activeRunningTurn = makeTurn({
      id: 'turn-1',
      threadId: 'thread-1',
      status: 'inProgress',
    })

    await harness.controller.interrupt()
    expect(harness.api.interruptTurn).toHaveBeenCalledWith(
      'thread-1',
      'turn-1',
      {},
    )
  })
})
