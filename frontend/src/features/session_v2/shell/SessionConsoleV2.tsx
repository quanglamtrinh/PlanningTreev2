import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { PendingServerRequest, SessionTurn } from '../contracts'
import {
  forkThreadV2,
  initializeSessionV2,
  interruptTurnV2,
  listLoadedThreadsV2,
  listPendingRequestsV2,
  listThreadsV2,
  listThreadTurnsV2,
  openThreadEventsStreamV2,
  readThreadV2,
  rejectPendingRequestV2,
  resolvePendingRequestV2,
  resumeThreadV2,
  startThreadV2,
  startTurnV2,
  steerTurnV2,
} from '../api/client'
import { parseSessionEvent } from '../state/sessionEventParser'
import { useConnectionStore } from '../store/connectionStore'
import { usePendingRequestsStore } from '../store/pendingRequestsStore'
import { useThreadSessionStore } from '../store/threadSessionStore'
import { ApprovalOverlay } from '../components/ApprovalOverlay'
import { ComposerPane } from '../components/ComposerPane'
import { McpElicitationOverlay } from '../components/McpElicitationOverlay'
import { RequestUserInputOverlay } from '../components/RequestUserInputOverlay'
import { ThreadListPanel } from '../components/ThreadListPanel'
import { TranscriptPanel } from '../components/TranscriptPanel'
import styles from './SessionConsoleV2.module.css'

const EVENT_METHODS: string[] = [
  'thread/started',
  'thread/status/changed',
  'thread/closed',
  'thread/archived',
  'thread/unarchived',
  'thread/name/updated',
  'thread/tokenUsage/updated',
  'turn/started',
  'turn/completed',
  'item/started',
  'item/completed',
  'item/agentMessage/delta',
  'item/plan/delta',
  'item/reasoning/summaryTextDelta',
  'item/reasoning/summaryPartAdded',
  'item/reasoning/textDelta',
  'item/commandExecution/outputDelta',
  'item/fileChange/outputDelta',
  'serverRequest/resolved',
  'error',
]

function actionId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function upsertTurnList(existing: SessionTurn[], nextTurn: SessionTurn): SessionTurn[] {
  const index = existing.findIndex((turn) => turn.id === nextTurn.id)
  if (index < 0) {
    return [...existing, nextTurn]
  }
  const updated = [...existing]
  updated[index] = nextTurn
  return updated
}

export function SessionConsoleV2() {
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [isBootstrapping, setIsBootstrapping] = useState(false)
  const reconnectTimerRef = useRef<number | null>(null)
  const pollTimerRef = useRef<number | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)

  const {
    threadsById,
    threadOrder,
    turnsByThread,
    itemsByTurn,
    activeThreadId,
    lastEventIdByThread,
    gapDetectedByThread,
    setThreadList,
    upsertThread,
    setActiveThreadId,
    setThreadTurns,
    applyEvent,
    markStreamConnected,
    markStreamDisconnected,
    markStreamReconnect,
    clearGapDetected,
    clear: clearThreadSessionStore,
  } = useThreadSessionStore(
    useShallow((state) => ({
      threadsById: state.threadsById,
      threadOrder: state.threadOrder,
      turnsByThread: state.turnsByThread,
      itemsByTurn: state.itemsByTurn,
      activeThreadId: state.activeThreadId,
      lastEventIdByThread: state.lastEventIdByThread,
      gapDetectedByThread: state.gapDetectedByThread,
      setThreadList: state.setThreadList,
      upsertThread: state.upsertThread,
      setActiveThreadId: state.setActiveThreadId,
      setThreadTurns: state.setThreadTurns,
      applyEvent: state.applyEvent,
      markStreamConnected: state.markStreamConnected,
      markStreamDisconnected: state.markStreamDisconnected,
      markStreamReconnect: state.markStreamReconnect,
      clearGapDetected: state.clearGapDetected,
      clear: state.clear,
    })),
  )

  const { connection, setPhase, setInitialized, setError, reset: resetConnectionStore } = useConnectionStore(
    useShallow((state) => ({
      connection: state.connection,
      setPhase: state.setPhase,
      setInitialized: state.setInitialized,
      setError: state.setError,
      reset: state.reset,
    })),
  )

  const {
    pendingById,
    queue,
    activeRequestId,
    hydrateFromServer,
    markSubmitted,
    markResolved,
    markRejected,
    setActiveRequest,
    clear: clearPendingRequestsStore,
  } = usePendingRequestsStore(
    useShallow((state) => ({
      pendingById: state.pendingById,
      queue: state.queue,
      activeRequestId: state.activeRequestId,
      hydrateFromServer: state.hydrateFromServer,
      markSubmitted: state.markSubmitted,
      markResolved: state.markResolved,
      markRejected: state.markRejected,
      setActiveRequest: state.setActiveRequest,
      clear: state.clear,
    })),
  )

  const threads = useMemo(
    () => threadOrder.map((threadId) => threadsById[threadId]).filter((thread): thread is NonNullable<typeof thread> => Boolean(thread)),
    [threadOrder, threadsById],
  )

  const activeTurns = useMemo(
    () => (activeThreadId ? turnsByThread[activeThreadId] ?? [] : []),
    [activeThreadId, turnsByThread],
  )
  const activeThread = useMemo(
    () => (activeThreadId ? threadsById[activeThreadId] ?? null : null),
    [activeThreadId, threadsById],
  )

  const activeRunningTurn = useMemo(() => {
    const candidates = [...activeTurns]
      .reverse()
      .find((turn) => turn.status === 'inProgress' || turn.status === 'waitingUserInput')
    return candidates ?? null
  }, [activeTurns])

  const activeRequest: PendingServerRequest | null = activeRequestId ? (pendingById[activeRequestId] ?? null) : null

  const closeStream = useCallback((threadId: string | null) => {
    if (threadId) {
      markStreamDisconnected(threadId)
    }
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (reconnectTimerRef.current !== null) {
      window.clearTimeout(reconnectTimerRef.current)
      reconnectTimerRef.current = null
    }
  }, [markStreamDisconnected])

  const hydrateThreadState = useCallback(async (threadId: string) => {
    const read = await readThreadV2(threadId, false)
    upsertThread(read.thread)
    const turns = await listThreadTurnsV2(threadId, { limit: 200 })
    setThreadTurns(threadId, turns.data)
  }, [setThreadTurns, upsertThread])

  const ensureThreadReady = useCallback(async (threadId: string) => {
    const resumed = await resumeThreadV2(threadId, {})
    upsertThread(resumed.thread)
    await hydrateThreadState(threadId)
  }, [hydrateThreadState, upsertThread])

  const openStream = useCallback((threadId: string) => {
    closeStream(threadId)
    clearGapDetected(threadId)
    const cursorEventId = lastEventIdByThread[threadId] ?? null
    const stream = openThreadEventsStreamV2(threadId, { cursorEventId })
    eventSourceRef.current = stream

    stream.onopen = () => {
      markStreamConnected(threadId)
      setRuntimeError(null)
    }

    stream.onerror = () => {
      markStreamDisconnected(threadId)
      markStreamReconnect(threadId)
      if (reconnectTimerRef.current !== null) {
        window.clearTimeout(reconnectTimerRef.current)
      }
      reconnectTimerRef.current = window.setTimeout(() => {
        openStream(threadId)
      }, 1000)
    }

    const handler = (event: MessageEvent) => {
      const parsed = parseSessionEvent(event.data)
      if (!parsed) {
        return
      }
      applyEvent(parsed)
      const state = useThreadSessionStore.getState()
      if (state.gapDetectedByThread[threadId]) {
        clearGapDetected(threadId)
        closeStream(threadId)
        openStream(threadId)
      }
    }

    for (const method of EVENT_METHODS) {
      stream.addEventListener(method, handler as EventListener)
    }
  }, [
    applyEvent,
    closeStream,
    clearGapDetected,
    lastEventIdByThread,
    markStreamConnected,
    markStreamDisconnected,
    markStreamReconnect,
  ])

  const pollPendingRequests = useCallback(async () => {
    try {
      const pending = await listPendingRequestsV2()
      hydrateFromServer(pending.data)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [hydrateFromServer])

  const schedulePendingPoll = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
    const intervalMs = activeRunningTurn || queue.length > 0 ? 400 : 2000
    pollTimerRef.current = window.setTimeout(async () => {
      await pollPendingRequests()
      schedulePendingPoll()
    }, intervalMs)
  }, [activeRunningTurn, pollPendingRequests, queue.length])

  const bootstrap = useCallback(async () => {
    setIsBootstrapping(true)
    setPhase('connecting')
    try {
      const initialized = await initializeSessionV2()
      setInitialized(
        initialized.connection.clientName ?? 'PlanningTree Session V2',
        initialized.connection.serverVersion ?? null,
      )

      let selectedThreadId: string | null = null

      const loaded = await listLoadedThreadsV2({ limit: 20 })
      if (loaded.data.length > 0) {
        selectedThreadId = loaded.data[0]
      }

      if (!selectedThreadId) {
        const listed = await listThreadsV2({ limit: 50 })
        setThreadList(listed.data)
        selectedThreadId = listed.data[0]?.id ?? null
      }

      if (!selectedThreadId) {
        const created = await startThreadV2({ modelProvider: 'openai' })
        upsertThread(created.thread)
        setThreadList([created.thread])
        selectedThreadId = created.thread.id
      }

      if (selectedThreadId) {
        await ensureThreadReady(selectedThreadId)
        setActiveThreadId(selectedThreadId)
      }
      setRuntimeError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
      setError({
        code: 'ERR_INTERNAL',
        message,
      })
    } finally {
      setIsBootstrapping(false)
    }
  }, [ensureThreadReady, setActiveThreadId, setError, setInitialized, setPhase, setThreadList, upsertThread])

  useEffect(() => {
    void bootstrap()
    return () => {
      closeStream(useThreadSessionStore.getState().activeThreadId)
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current)
        pollTimerRef.current = null
      }
      clearPendingRequestsStore()
      clearThreadSessionStore()
      resetConnectionStore()
    }
  }, [bootstrap, clearPendingRequestsStore, clearThreadSessionStore, closeStream, resetConnectionStore])

  useEffect(() => {
    if (!activeThreadId) {
      return
    }
    openStream(activeThreadId)
    void pollPendingRequests()
    schedulePendingPoll()
    return () => {
      closeStream(activeThreadId)
      if (pollTimerRef.current !== null) {
        window.clearTimeout(pollTimerRef.current)
        pollTimerRef.current = null
      }
    }
  }, [activeThreadId, closeStream, openStream, pollPendingRequests, schedulePendingPoll])

  useEffect(() => {
    if (!activeRequestId && queue.length > 0) {
      setActiveRequest(queue[0])
    }
  }, [activeRequestId, queue, setActiveRequest])

  const handleSelectThread = useCallback(async (threadId: string) => {
    setActiveThreadId(threadId)
    try {
      await ensureThreadReady(threadId)
      setRuntimeError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [ensureThreadReady, setActiveThreadId])

  const handleCreateThread = useCallback(async () => {
    try {
      const created = await startThreadV2({ modelProvider: 'openai' })
      upsertThread(created.thread)
      setActiveThreadId(created.thread.id)
      await ensureThreadReady(created.thread.id)
      setRuntimeError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [ensureThreadReady, setActiveThreadId, upsertThread])

  const handleForkThread = useCallback(async (threadId: string) => {
    try {
      const forked = await forkThreadV2(threadId, {})
      upsertThread(forked.thread)
      setActiveThreadId(forked.thread.id)
      await ensureThreadReady(forked.thread.id)
      setRuntimeError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [ensureThreadReady, setActiveThreadId, upsertThread])

  const handleRefresh = useCallback(async () => {
    try {
      const listed = await listThreadsV2({ limit: 50 })
      setThreadList(listed.data)
      if (activeThreadId) {
        await hydrateThreadState(activeThreadId)
      }
      setRuntimeError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [activeThreadId, hydrateThreadState, setThreadList])

  const handleSubmit = useCallback(async (payload: { input: Array<Record<string, unknown>>; text: string }) => {
    if (!activeThreadId) {
      return
    }
    try {
      if (activeRunningTurn) {
        const result = await steerTurnV2(activeThreadId, activeRunningTurn.id, {
          clientActionId: actionId(),
          expectedTurnId: activeRunningTurn.id,
          input: payload.input,
        })
        const nextTurns = upsertTurnList(activeTurns, result.turn)
        setThreadTurns(activeThreadId, nextTurns)
      } else {
        const result = await startTurnV2(activeThreadId, {
          clientActionId: actionId(),
          input: payload.input,
        })
        const nextTurns = upsertTurnList(activeTurns, result.turn)
        setThreadTurns(activeThreadId, nextTurns)
      }
      setRuntimeError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [activeRunningTurn, activeThreadId, activeTurns, setThreadTurns])

  const handleInterrupt = useCallback(async () => {
    if (!activeThreadId || !activeRunningTurn) {
      return
    }
    try {
      await interruptTurnV2(activeThreadId, activeRunningTurn.id, { clientActionId: actionId() })
      setRuntimeError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [activeRunningTurn, activeThreadId])

  const resolveRequest = useCallback(async (result: Record<string, unknown>) => {
    if (!activeRequest) {
      return
    }
    await resolvePendingRequestV2(activeRequest.requestId, {
      resolutionKey: actionId(),
      result,
    })
    markSubmitted(activeRequest.requestId)
  }, [activeRequest, markSubmitted])

  const rejectRequest = useCallback(async (reason?: string | null) => {
    if (!activeRequest) {
      return
    }
    await rejectPendingRequestV2(activeRequest.requestId, {
      resolutionKey: actionId(),
      reason: reason ?? null,
    })
    markSubmitted(activeRequest.requestId)
  }, [activeRequest, markSubmitted])

  useEffect(() => {
    if (!activeRequest) {
      return
    }
    const current = pendingById[activeRequest.requestId]
    if (!current) {
      markResolved(activeRequest.requestId)
      return
    }
    if (current.status === 'resolved') {
      markResolved(current.requestId)
    } else if (current.status === 'rejected' || current.status === 'expired') {
      markRejected(current.requestId)
    }
  }, [activeRequest, markRejected, markResolved, pendingById])

  return (
    <section className={styles.console}>
      <ThreadListPanel
        threads={threads}
        activeThreadId={activeThreadId}
        onCreateThread={() => void handleCreateThread()}
        onRefresh={() => void handleRefresh()}
        onSelectThread={(threadId) => void handleSelectThread(threadId)}
        onResumeThread={(threadId) => void handleSelectThread(threadId)}
        onForkThread={(threadId) => void handleForkThread(threadId)}
      />

      <main className={styles.mainPane}>
        <header className={styles.statusBar}>
          <div>
            <strong>Session</strong>
            <span className={styles.muted}>connection: {connection.phase}</span>
          </div>
          <div className={styles.statusMeta}>
            <span>thread: {activeThread?.name ?? activeThreadId ?? 'none'}</span>
            <span>running: {activeRunningTurn ? 'yes' : 'no'}</span>
            <span>queue: {queue.length}</span>
            <span>gap: {activeThreadId ? (gapDetectedByThread[activeThreadId] ? 'yes' : 'no') : 'n/a'}</span>
          </div>
        </header>

        {isBootstrapping ? <div className={styles.banner}>Bootstrapping Session V2...</div> : null}
        {runtimeError ? <div className={styles.errorBanner}>{runtimeError}</div> : null}

        <TranscriptPanel
          threadId={activeThreadId}
          turns={activeTurns}
          itemsByTurn={itemsByTurn}
        />

        <ComposerPane
          isTurnRunning={Boolean(activeRunningTurn)}
          disabled={!activeThreadId || connection.phase === 'error'}
          onSubmit={handleSubmit}
          onInterrupt={handleInterrupt}
        />
      </main>

      {activeRequest?.method === 'item/tool/requestUserInput' ? (
        <RequestUserInputOverlay request={activeRequest} onResolve={resolveRequest} onReject={rejectRequest} />
      ) : null}

      {activeRequest?.method === 'mcpServer/elicitation/request' ? (
        <McpElicitationOverlay request={activeRequest} onResolve={resolveRequest} onReject={rejectRequest} />
      ) : null}

      {activeRequest &&
      activeRequest.method !== 'item/tool/requestUserInput' &&
      activeRequest.method !== 'mcpServer/elicitation/request' ? (
        <ApprovalOverlay request={activeRequest} onResolve={resolveRequest} onReject={rejectRequest} />
      ) : null}
    </section>
  )
}
