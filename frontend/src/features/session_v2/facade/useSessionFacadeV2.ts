import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import type { ComposerSubmitPayload } from '../components/ComposerPane'
import type { PendingServerRequest, SessionItem, SessionThread, SessionTurn, ThreadStatus } from '../contracts'
import { createSessionEventStreamController, type SessionEventStreamController } from './sessionEventStreamController'
import {
  createSessionRuntimeController,
  type ComposerModelOption,
  type RuntimeSnapshot,
  type SessionBootstrapPolicy,
  type SessionRuntimeController,
} from './sessionRuntimeController'
import { useConnectionStore } from '../store/connectionStore'
import { usePendingRequestsStore } from '../store/pendingRequestsStore'
import {
  selectActiveItemsByTurn,
  selectActiveRunningTurn,
  selectActiveThread,
  selectActiveTurns,
  selectThreadsSorted,
  useThreadSessionStore,
} from '../store/threadSessionStore'

type RuntimeOwnership = {
  ownerCount: number
  lifecycleGeneration: number
}

type RuntimeLease = {
  lifecycleGeneration: number
  isPrimary: boolean
  released: boolean
}

const runtimeOwnership: RuntimeOwnership = {
  ownerCount: 0,
  lifecycleGeneration: 0,
}

function getCurrentLifecycleGeneration(): number {
  return runtimeOwnership.lifecycleGeneration
}

function acquireRuntimeLease(): RuntimeLease {
  const isPrimary = runtimeOwnership.ownerCount === 0
  runtimeOwnership.ownerCount += 1
  if (isPrimary) {
    runtimeOwnership.lifecycleGeneration += 1
  }
  return {
    lifecycleGeneration: runtimeOwnership.lifecycleGeneration,
    isPrimary,
    released: false,
  }
}

function releaseRuntimeLease(lease: RuntimeLease): number {
  if (lease.released) {
    return runtimeOwnership.ownerCount
  }

  lease.released = true
  runtimeOwnership.ownerCount = Math.max(0, runtimeOwnership.ownerCount - 1)
  if (runtimeOwnership.ownerCount === 0) {
    runtimeOwnership.lifecycleGeneration += 1
  }
  return runtimeOwnership.ownerCount
}

export type SessionFacadeState = {
  connection: ReturnType<typeof useConnectionStore.getState>['connection']
  threads: SessionThread[]
  activeThreadId: string | null
  activeThread: SessionThread | null
  activeTurns: SessionTurn[]
  activeItemsByTurn: Record<string, SessionItem[]>
  activeRunningTurn: SessionTurn | null
  activeRequest: PendingServerRequest | null
  modelOptions: ComposerModelOption[]
  selectedModel: string | null
  runtimeError: string | null
  isBootstrapping: boolean
  isSelectingThread: boolean
  isActiveThreadReady: boolean
  isModelLoading: boolean
  queueLength: number
  gapDetected: boolean
  streamConnected: boolean
  reconnectCount: number
  threadStatus: ThreadStatus | null
  tokenUsage: Record<string, unknown> | null
  lastPollAtMs: number | null
}

export type SessionFacadeCommands = {
  bootstrap: () => Promise<void>
  selectThread: (threadId: string | null) => Promise<void>
  createThread: () => Promise<void>
  forkThread: (threadId: string) => Promise<void>
  refreshThreads: () => Promise<void>
  setModel: (model: string) => void
  submit: (payload: ComposerSubmitPayload) => Promise<void>
  interrupt: () => Promise<void>
  resolveRequest: (result: Record<string, unknown>) => Promise<void>
  rejectRequest: (reason?: string | null) => Promise<void>
}

export type SessionFacadeV2 = {
  state: SessionFacadeState
  commands: SessionFacadeCommands
}

export type SessionFacadePendingRequestScope = 'global' | 'activeThread'

export type SessionFacadeBootstrapPolicy = SessionBootstrapPolicy & {
  autoBootstrapOnMount: boolean
}

export type SessionFacadeOptions = {
  bootstrapPolicy?: Partial<SessionFacadeBootstrapPolicy>
  pendingRequestScope?: SessionFacadePendingRequestScope
}

const DEFAULT_BOOTSTRAP_POLICY: SessionFacadeBootstrapPolicy = {
  autoBootstrapOnMount: true,
  autoSelectInitialThread: true,
  autoCreateThreadWhenEmpty: true,
}

function resolveBootstrapPolicy(
  policy?: Partial<SessionFacadeBootstrapPolicy>,
): SessionFacadeBootstrapPolicy {
  return {
    autoBootstrapOnMount:
      policy?.autoBootstrapOnMount ?? DEFAULT_BOOTSTRAP_POLICY.autoBootstrapOnMount,
    autoSelectInitialThread:
      policy?.autoSelectInitialThread ?? DEFAULT_BOOTSTRAP_POLICY.autoSelectInitialThread,
    autoCreateThreadWhenEmpty:
      policy?.autoCreateThreadWhenEmpty ?? DEFAULT_BOOTSTRAP_POLICY.autoCreateThreadWhenEmpty,
  }
}

function resolvePendingRequestScope(
  scope?: SessionFacadePendingRequestScope,
): SessionFacadePendingRequestScope {
  return scope === 'activeThread' ? 'activeThread' : 'global'
}

function resolveActiveRequestId(options: {
  activeRequestId: string | null
  queue: string[]
  pendingById: Record<string, PendingServerRequest>
  activeThreadId: string | null
  pendingRequestScope: SessionFacadePendingRequestScope
}): string | null {
  const { activeRequestId, queue, pendingById, activeThreadId, pendingRequestScope } = options
  const scopedQueue =
    pendingRequestScope === 'activeThread'
      ? queue.filter((requestId) => pendingById[requestId]?.threadId === activeThreadId)
      : queue

  if (activeRequestId && scopedQueue.includes(activeRequestId)) {
    return activeRequestId
  }
  return scopedQueue[0] ?? null
}

function resolveSelectedModel(
  activeThreadId: string | null,
  activeThread: SessionThread | null,
  modelOptions: ComposerModelOption[],
  selectedModelByThread: Record<string, string>,
): string | null {
  if (!activeThreadId) {
    return null
  }

  const selectedFromState = selectedModelByThread[activeThreadId]
  if (typeof selectedFromState === 'string' && selectedFromState.trim().length > 0) {
    return selectedFromState
  }

  const threadModel = typeof activeThread?.model === 'string' ? activeThread.model.trim() : ''
  if (threadModel) {
    return threadModel
  }

  return modelOptions.find((option) => option.isDefault)?.value ?? modelOptions[0]?.value ?? null
}

export function useSessionFacadeV2(options?: SessionFacadeOptions): SessionFacadeV2 {
  const threadStoreState = useThreadSessionStore()
  const connectionStoreState = useConnectionStore()
  const pendingRequestsStoreState = usePendingRequestsStore()
  const bootstrapPolicy = resolveBootstrapPolicy(options?.bootstrapPolicy)
  const pendingRequestScope = resolvePendingRequestScope(options?.pendingRequestScope)

  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [isBootstrapping, setIsBootstrapping] = useState(false)
  const [isSelectingThread, setIsSelectingThread] = useState(false)
  const [isModelLoading, setIsModelLoading] = useState(false)
  const [modelOptions, setModelOptions] = useState<ComposerModelOption[]>([])
  const [selectedModelByThread, setSelectedModelByThread] = useState<Record<string, string>>({})

  const runtimeControllerRef = useRef<SessionRuntimeController | null>(null)
  const streamControllerRef = useRef<SessionEventStreamController | null>(null)
  const runtimeSnapshotRef = useRef<RuntimeSnapshot>({
    activeThreadId: null,
    activeTurns: [],
    activeRunningTurn: null,
    selectedModel: null,
    activeRequest: null,
  })
  const leaseRef = useRef<RuntimeLease | null>(null)
  const disposedRef = useRef(false)
  const pollTimerRef = useRef<number | null>(null)
  const pollGenerationRef = useRef(0)
  const selectingOperationCountRef = useRef(0)

  const threads = useMemo(() => selectThreadsSorted(threadStoreState), [threadStoreState])
  const activeThread = useMemo(() => selectActiveThread(threadStoreState), [threadStoreState])
  const activeTurns = useMemo(() => selectActiveTurns(threadStoreState), [threadStoreState])
  const activeItemsByTurn = useMemo(() => selectActiveItemsByTurn(threadStoreState), [threadStoreState])
  const activeRunningTurn = useMemo(() => selectActiveRunningTurn(threadStoreState), [threadStoreState])

  const activeRequest = useMemo(() => {
    const requestId = resolveActiveRequestId({
      activeRequestId: pendingRequestsStoreState.activeRequestId,
      queue: pendingRequestsStoreState.queue,
      pendingById: pendingRequestsStoreState.pendingById,
      activeThreadId: threadStoreState.activeThreadId,
      pendingRequestScope,
    })
    if (!requestId) {
      return null
    }
    return pendingRequestsStoreState.pendingById[requestId] ?? null
  }, [
    pendingRequestScope,
    pendingRequestsStoreState.activeRequestId,
    pendingRequestsStoreState.pendingById,
    pendingRequestsStoreState.queue,
    threadStoreState.activeThreadId,
  ])

  const selectedModel = useMemo(() => {
    return resolveSelectedModel(threadStoreState.activeThreadId, activeThread, modelOptions, selectedModelByThread)
  }, [activeThread, modelOptions, selectedModelByThread, threadStoreState.activeThreadId])

  const threadStatus = useMemo(() => {
    const activeThreadId = threadStoreState.activeThreadId
    if (!activeThreadId) {
      return null
    }
    return threadStoreState.threadStatus[activeThreadId] ?? activeThread?.status ?? null
  }, [activeThread, threadStoreState.activeThreadId, threadStoreState.threadStatus])

  const isActiveThreadReady = useMemo(() => {
    if (!threadStoreState.activeThreadId || isSelectingThread) {
      return false
    }
    if (!threadStatus) {
      return false
    }
    return threadStatus.type !== 'notLoaded'
  }, [isSelectingThread, threadStatus, threadStoreState.activeThreadId])

  const tokenUsage = useMemo(() => {
    const activeThreadId = threadStoreState.activeThreadId
    if (!activeThreadId) {
      return null
    }
    return threadStoreState.tokenUsageByThread[activeThreadId] ?? null
  }, [threadStoreState.activeThreadId, threadStoreState.tokenUsageByThread])

  const queueLength = pendingRequestsStoreState.queue.length
  const gapDetected = threadStoreState.activeThreadId
    ? Boolean(threadStoreState.gapDetectedByThread[threadStoreState.activeThreadId])
    : false
  const streamConnected = threadStoreState.activeThreadId
    ? Boolean(threadStoreState.streamState.connectedByThread[threadStoreState.activeThreadId])
    : false
  const reconnectCount = threadStoreState.activeThreadId
    ? threadStoreState.streamState.reconnectCountByThread[threadStoreState.activeThreadId] ?? 0
    : 0

  runtimeSnapshotRef.current = {
    activeThreadId: threadStoreState.activeThreadId,
    activeTurns,
    activeRunningTurn,
    selectedModel,
    activeRequest,
  }

  const isCurrentLifecycle = useCallback(() => {
    const lease = leaseRef.current
    if (disposedRef.current || !lease) {
      return false
    }
    return lease.lifecycleGeneration === getCurrentLifecycleGeneration()
  }, [])

  const clearPendingPollTimer = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  if (!runtimeControllerRef.current) {
    runtimeControllerRef.current = createSessionRuntimeController({
      getThreadState: () => useThreadSessionStore.getState(),
      getRuntimeSnapshot: () => runtimeSnapshotRef.current,
      setThreadList: (rows) => useThreadSessionStore.getState().setThreadList(rows),
      upsertThread: (thread, options) => useThreadSessionStore.getState().upsertThread(thread, options),
      markThreadActivity: (threadId, updatedAt) => useThreadSessionStore.getState().markThreadActivity(threadId, updatedAt),
      setActiveThreadId: (threadId) => useThreadSessionStore.getState().setActiveThreadId(threadId),
      setThreadTurns: (threadId, turns) => useThreadSessionStore.getState().setThreadTurns(threadId, turns),
      hydratePendingRequests: (rows) => usePendingRequestsStore.getState().hydrateFromServer(rows),
      markPendingRequestSubmitted: (requestId) => usePendingRequestsStore.getState().markSubmitted(requestId),
      setConnectionPhase: (phase) => useConnectionStore.getState().setPhase(phase),
      setConnectionInitialized: (clientName, serverVersion) =>
        useConnectionStore.getState().setInitialized(clientName, serverVersion),
      setConnectionError: (error) => useConnectionStore.getState().setError(error),
      setRuntimeError,
      setIsBootstrapping,
      setIsModelLoading,
      setModelOptions,
      setLastPendingPollAtMs: (value) => {
        usePendingRequestsStore.setState((state) => ({
          ...state,
          lastPollAtMs: value,
        }))
      },
      isDisposed: () => !isCurrentLifecycle(),
    })
  }

  if (!streamControllerRef.current) {
    streamControllerRef.current = createSessionEventStreamController({
      applyEventsBatch: (envelopes) => useThreadSessionStore.getState().applyEventsBatch(envelopes),
      markStreamConnected: (threadId) => useThreadSessionStore.getState().markStreamConnected(threadId),
      markStreamDisconnected: (threadId) => useThreadSessionStore.getState().markStreamDisconnected(threadId),
      markStreamReconnect: (threadId) => useThreadSessionStore.getState().markStreamReconnect(threadId),
      clearGapDetected: (threadId) => useThreadSessionStore.getState().clearGapDetected(threadId),
      getLastEventId: (threadId) => useThreadSessionStore.getState().lastEventIdByThread[threadId] ?? null,
      getGapDetected: (threadId) => Boolean(useThreadSessionStore.getState().gapDetectedByThread[threadId]),
      onRuntimeError: setRuntimeError,
    })
  }

  const pollPendingRequests = useCallback(async () => {
    if (!isCurrentLifecycle()) {
      return
    }
    const runtimeController = runtimeControllerRef.current
    if (!runtimeController) {
      return
    }
    await runtimeController.pollPendingRequests()
  }, [isCurrentLifecycle])

  const schedulePendingPoll = useCallback(() => {
    if (!isCurrentLifecycle()) {
      return
    }

    pollGenerationRef.current += 1
    const generation = pollGenerationRef.current

    clearPendingPollTimer()
    const intervalMs = activeRunningTurn || queueLength > 0 ? 400 : 2000
    pollTimerRef.current = window.setTimeout(async () => {
      if (!isCurrentLifecycle() || pollGenerationRef.current !== generation) {
        return
      }
      await pollPendingRequests()
      if (!isCurrentLifecycle() || pollGenerationRef.current !== generation) {
        return
      }
      schedulePendingPoll()
    }, intervalMs)
  }, [activeRunningTurn, clearPendingPollTimer, isCurrentLifecycle, pollPendingRequests, queueLength])

  useEffect(() => {
    const lease = acquireRuntimeLease()
    leaseRef.current = lease
    disposedRef.current = false

    if (lease.isPrimary && bootstrapPolicy.autoBootstrapOnMount) {
      void runtimeControllerRef.current?.bootstrap({
        autoSelectInitialThread: bootstrapPolicy.autoSelectInitialThread,
        autoCreateThreadWhenEmpty: bootstrapPolicy.autoCreateThreadWhenEmpty,
      })
    }

    return () => {
      disposedRef.current = true
      pollGenerationRef.current += 1
      clearPendingPollTimer()
      const activeThreadId = useThreadSessionStore.getState().activeThreadId
      streamControllerRef.current?.close(activeThreadId)
      streamControllerRef.current?.dispose()
      runtimeControllerRef.current?.dispose()
      const remainingOwners = releaseRuntimeLease(lease)
      leaseRef.current = null

      if (remainingOwners === 0) {
        usePendingRequestsStore.getState().clear()
        useThreadSessionStore.getState().clear()
        useConnectionStore.getState().reset()
      }
    }
  }, [
    bootstrapPolicy.autoBootstrapOnMount,
    bootstrapPolicy.autoCreateThreadWhenEmpty,
    bootstrapPolicy.autoSelectInitialThread,
    clearPendingPollTimer,
  ])

  useEffect(() => {
    if (!threadStoreState.activeThreadId || !leaseRef.current?.isPrimary) {
      return
    }

    const activeThreadId = threadStoreState.activeThreadId
    streamControllerRef.current?.open(activeThreadId)
    void pollPendingRequests()
    schedulePendingPoll()

    return () => {
      pollGenerationRef.current += 1
      clearPendingPollTimer()
      streamControllerRef.current?.close(activeThreadId)
    }
  }, [clearPendingPollTimer, pollPendingRequests, schedulePendingPoll, threadStoreState.activeThreadId])

  useEffect(() => {
    const resolvedActiveRequestId = activeRequest?.requestId ?? null
    if (pendingRequestsStoreState.activeRequestId === resolvedActiveRequestId) {
      return
    }
    usePendingRequestsStore.getState().setActiveRequest(resolvedActiveRequestId)
  }, [activeRequest?.requestId, pendingRequestsStoreState.activeRequestId])

  useEffect(() => {
    const activeThreadId = threadStoreState.activeThreadId
    if (!activeThreadId || !selectedModel) {
      return
    }

    setSelectedModelByThread((previous) => {
      if (previous[activeThreadId]) {
        return previous
      }
      return {
        ...previous,
        [activeThreadId]: selectedModel,
      }
    })
  }, [selectedModel, threadStoreState.activeThreadId])

  useEffect(() => {
    if (!activeRequest) {
      return
    }

    const current = pendingRequestsStoreState.pendingById[activeRequest.requestId]
    if (!current) {
      usePendingRequestsStore.getState().markResolved(activeRequest.requestId)
      return
    }

    if (current.status === 'resolved') {
      usePendingRequestsStore.getState().markResolved(current.requestId)
      return
    }

    if (current.status === 'rejected' || current.status === 'expired') {
      usePendingRequestsStore.getState().markRejected(current.requestId)
    }
  }, [activeRequest, pendingRequestsStoreState.pendingById])

  const runSelectingCommand = useCallback(async (run: () => Promise<void>) => {
    selectingOperationCountRef.current += 1
    setIsSelectingThread(true)
    try {
      await run()
    } finally {
      selectingOperationCountRef.current = Math.max(0, selectingOperationCountRef.current - 1)
      if (selectingOperationCountRef.current === 0) {
        setIsSelectingThread(false)
      }
    }
  }, [])

  const bootstrap = useCallback(async () => {
    await runtimeControllerRef.current?.bootstrap({
      autoSelectInitialThread: bootstrapPolicy.autoSelectInitialThread,
      autoCreateThreadWhenEmpty: bootstrapPolicy.autoCreateThreadWhenEmpty,
    })
  }, [bootstrapPolicy.autoCreateThreadWhenEmpty, bootstrapPolicy.autoSelectInitialThread])

  const selectThread = useCallback(async (threadId: string | null) => {
    if (threadId === null) {
      pollGenerationRef.current += 1
      clearPendingPollTimer()
      const activeThreadId = useThreadSessionStore.getState().activeThreadId
      streamControllerRef.current?.close(activeThreadId)
    }

    await runSelectingCommand(async () => {
      await runtimeControllerRef.current?.selectThread(threadId)
    })
  }, [clearPendingPollTimer, runSelectingCommand])

  const createThread = useCallback(async () => {
    await runSelectingCommand(async () => {
      await runtimeControllerRef.current?.createThread()
    })
  }, [runSelectingCommand])

  const forkThread = useCallback(async (threadId: string) => {
    await runSelectingCommand(async () => {
      await runtimeControllerRef.current?.forkThread(threadId)
    })
  }, [runSelectingCommand])

  const refreshThreads = useCallback(async () => {
    await runtimeControllerRef.current?.refreshThreads()
  }, [])

  const setModel = useCallback((model: string) => {
    const activeThreadId = useThreadSessionStore.getState().activeThreadId
    if (!activeThreadId) {
      return
    }

    setSelectedModelByThread((previous) => ({
      ...previous,
      [activeThreadId]: model,
    }))
  }, [])

  const submit = useCallback(async (payload: ComposerSubmitPayload) => {
    if (!payload.model && selectedModel) {
      await runtimeControllerRef.current?.submit({
        ...payload,
        model: selectedModel,
      })
      return
    }
    await runtimeControllerRef.current?.submit(payload)
  }, [selectedModel])

  const interrupt = useCallback(async () => {
    await runtimeControllerRef.current?.interrupt()
  }, [])

  const resolveRequest = useCallback(async (result: Record<string, unknown>) => {
    await runtimeControllerRef.current?.resolveRequest(result)
  }, [])

  const rejectRequest = useCallback(async (reason?: string | null) => {
    await runtimeControllerRef.current?.rejectRequest(reason)
  }, [])

  const state: SessionFacadeState = {
    connection: connectionStoreState.connection,
    threads,
    activeThreadId: threadStoreState.activeThreadId,
    activeThread,
    activeTurns,
    activeItemsByTurn,
    activeRunningTurn,
    activeRequest,
    modelOptions,
    selectedModel,
    runtimeError,
    isBootstrapping,
    isSelectingThread,
    isActiveThreadReady,
    isModelLoading,
    queueLength,
    gapDetected,
    streamConnected,
    reconnectCount,
    threadStatus,
    tokenUsage,
    lastPollAtMs: pendingRequestsStoreState.lastPollAtMs,
  }

  const commands: SessionFacadeCommands = {
    bootstrap,
    selectThread,
    createThread,
    forkThread,
    refreshThreads,
    setModel,
    submit,
    interrupt,
    resolveRequest,
    rejectRequest,
  }

  return {
    state,
    commands,
  }
}

export function getSessionFacadeRuntimeOwnershipSnapshot(): RuntimeOwnership {
  return {
    ownerCount: runtimeOwnership.ownerCount,
    lifecycleGeneration: runtimeOwnership.lifecycleGeneration,
  }
}

export function resetSessionFacadeRuntimeOwnershipForTests(): void {
  runtimeOwnership.ownerCount = 0
  runtimeOwnership.lifecycleGeneration = 0
  useThreadSessionStore.getState().clear()
  usePendingRequestsStore.getState().clear()
  useConnectionStore.getState().reset()
}




