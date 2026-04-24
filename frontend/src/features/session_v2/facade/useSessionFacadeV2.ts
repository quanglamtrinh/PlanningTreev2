import { useCallback, useMemo, useRef, useState } from 'react'

import type { ComposerSubmitPayload } from '../components/ComposerPane'
import type {
  PendingServerRequest,
  SessionItem,
  SessionInputAction,
  SessionThread,
  SessionTurn,
  ThreadCreationPolicy,
  ThreadStatus,
  TurnExecutionPolicy,
} from '../contracts'
import { createSessionEventStreamController, type SessionEventStreamController } from './sessionEventStreamController'
import {
  createSessionActionId,
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
import { usePendingRequestLoop } from './usePendingRequestLoop'
import { useSessionRuntimeLease } from './useSessionRuntimeLease'
import { useSessionSelectionState } from './useSessionSelectionState'
import { useThreadModelSelection } from './useThreadModelSelection'

export {
  getSessionFacadeRuntimeOwnershipSnapshot,
  resetSessionFacadeRuntimeOwnershipForTests,
} from './useSessionRuntimeLease'

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
  bootstrap: (policy?: Partial<SessionFacadeBootstrapPolicy>) => Promise<void>
  selectThread: (threadId: string | null) => Promise<void>
  createThread: (policy?: ThreadCreationPolicy) => Promise<void>
  forkThread: (threadId: string) => Promise<void>
  refreshThreads: () => Promise<void>
  submitSessionAction: (action: SessionInputAction) => Promise<void>
  setModel: (model: string) => void
  submit: (payload: ComposerSubmitPayload, policy?: TurnExecutionPolicy) => Promise<void>
  interrupt: () => Promise<void>
  resolveRequest: (requestId: string, result: Record<string, unknown>) => Promise<void>
  rejectRequest: (requestId: string, reason?: string | null) => Promise<void>
}

export type SessionFacadeV2 = {
  state: SessionFacadeState
  commands: SessionFacadeCommands
}

export type SessionFacadePendingRequestScope = 'global' | 'activeThread'

export type SessionFacadeBootstrapPolicy = SessionBootstrapPolicy & {
  autoBootstrapOnMount: boolean
  threadCreationPolicy?: ThreadCreationPolicy
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
    threadCreationPolicy: policy?.threadCreationPolicy,
  }
}

function resolvePendingRequestScope(
  scope?: SessionFacadePendingRequestScope,
): SessionFacadePendingRequestScope {
  return scope === 'activeThread' ? 'activeThread' : 'global'
}

export function useSessionFacadeV2(options?: SessionFacadeOptions): SessionFacadeV2 {
  const threadStoreState = useThreadSessionStore()
  const connectionStoreState = useConnectionStore()
  const pendingRequestsStoreState = usePendingRequestsStore()
  const bootstrapPolicy = resolveBootstrapPolicy(options?.bootstrapPolicy)
  const pendingRequestScope = resolvePendingRequestScope(options?.pendingRequestScope)

  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [isBootstrapping, setIsBootstrapping] = useState(false)

  const runtimeControllerRef = useRef<SessionRuntimeController | null>(null)
  const streamControllerRef = useRef<SessionEventStreamController | null>(null)
  const runtimeSnapshotRef = useRef<RuntimeSnapshot>({
    activeThreadId: null,
    activeTurns: [],
    activeRunningTurn: null,
    selectedModel: null,
  })

  const threads = useMemo(() => selectThreadsSorted(threadStoreState), [threadStoreState])
  const activeThread = useMemo(() => selectActiveThread(threadStoreState), [threadStoreState])
  const activeTurns = useMemo(() => selectActiveTurns(threadStoreState), [threadStoreState])
  const activeItemsByTurn = useMemo(() => selectActiveItemsByTurn(threadStoreState), [threadStoreState])
  const activeRunningTurn = useMemo(() => selectActiveRunningTurn(threadStoreState), [threadStoreState])

  const {
    isModelLoading,
    setIsModelLoading,
    modelOptions,
    setModelOptions,
    selectedModel,
    setModel,
  } = useThreadModelSelection({
    activeThreadId: threadStoreState.activeThreadId,
    activeThread,
  })

  const { isCurrentLifecycle, isPrimaryLifecycleOwner } = useSessionRuntimeLease({
    bootstrapPolicy,
    runtimeControllerRef,
    streamControllerRef,
  })

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
      applyRequestEventsBatch: (envelopes) => usePendingRequestsStore.getState().applyRequestEventsBatch(envelopes),
      markStreamConnected: (threadId) => useThreadSessionStore.getState().markStreamConnected(threadId),
      markStreamDisconnected: (threadId) => useThreadSessionStore.getState().markStreamDisconnected(threadId),
      markStreamReconnect: (threadId) => useThreadSessionStore.getState().markStreamReconnect(threadId),
      clearGapDetected: (threadId) => useThreadSessionStore.getState().clearGapDetected(threadId),
      getLastEventId: (threadId) => useThreadSessionStore.getState().lastEventIdByThread[threadId] ?? null,
      getGapDetected: (threadId) => Boolean(useThreadSessionStore.getState().gapDetectedByThread[threadId]),
      onStreamConnected: () => {
        void runtimeControllerRef.current?.pollPendingRequests({ surfaceErrors: false })
      },
      onRuntimeError: setRuntimeError,
    })
  }

  const { activeRequest, stopPendingRequestLoop } = usePendingRequestLoop({
    activeThreadId: threadStoreState.activeThreadId,
    streamConnected,
    pendingRequestsStoreState,
    pendingRequestScope,
    runtimeControllerRef,
    streamControllerRef,
    isCurrentLifecycle,
    isPrimaryLifecycleOwner,
  })

  const { isSelectingThread, selectThread, createThread, forkThread } = useSessionSelectionState({
    runtimeControllerRef,
    streamControllerRef,
    stopPendingRequestLoop,
  })

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

  runtimeSnapshotRef.current = {
    activeThreadId: threadStoreState.activeThreadId,
    activeTurns,
    activeRunningTurn,
    selectedModel,
  }

  const bootstrap = useCallback(async (policy?: Partial<SessionFacadeBootstrapPolicy>) => {
    const resolvedPolicy = resolveBootstrapPolicy({
      ...bootstrapPolicy,
      ...(policy ?? {}),
    })
    await runtimeControllerRef.current?.bootstrap({
      autoSelectInitialThread: resolvedPolicy.autoSelectInitialThread,
      autoCreateThreadWhenEmpty: resolvedPolicy.autoCreateThreadWhenEmpty,
      threadCreationPolicy: resolvedPolicy.threadCreationPolicy,
    })
  }, [bootstrapPolicy])

  const refreshThreads = useCallback(async () => {
    await runtimeControllerRef.current?.refreshThreads()
  }, [])

  const submit = useCallback(async (payload: ComposerSubmitPayload, policy?: TurnExecutionPolicy) => {
    await runtimeControllerRef.current?.submit(payload, policy)
  }, [])

  const interrupt = useCallback(async () => {
    await runtimeControllerRef.current?.interrupt()
  }, [])

  const submitSessionAction = useCallback(async (action: SessionInputAction) => {
    await runtimeControllerRef.current?.submitSessionAction(action)
  }, [])

  const resolveRequest = useCallback(async (requestId: string, result: Record<string, unknown>) => {
    const normalizedRequestId = requestId.trim()
    if (!normalizedRequestId) {
      return
    }
    await runtimeControllerRef.current?.submitSessionAction({
      type: 'request.resolve',
      requestId: normalizedRequestId,
      result,
      resolutionKey: createSessionActionId(),
    })
  }, [])

  const rejectRequest = useCallback(async (requestId: string, reason?: string | null) => {
    const normalizedRequestId = requestId.trim()
    if (!normalizedRequestId) {
      return
    }
    await runtimeControllerRef.current?.submitSessionAction({
      type: 'request.reject',
      requestId: normalizedRequestId,
      reason: reason ?? null,
      resolutionKey: createSessionActionId(),
    })
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
    submitSessionAction,
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

