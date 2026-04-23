import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { PendingServerRequest, SessionEventEnvelope, SessionTurn } from '../contracts'
import {
  forkThreadV2,
  initializeSessionV2,
  interruptTurnV2,
  listModelsV2,
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
  type SessionModelEntryV2,
} from '../api/client'
import { parseSessionEvent } from '../state/sessionEventParser'
import { useConnectionStore } from '../store/connectionStore'
import { usePendingRequestsStore } from '../store/pendingRequestsStore'
import { useThreadSessionStore } from '../store/threadSessionStore'
import { ApprovalOverlay } from '../components/ApprovalOverlay'
import { ComposerPane, type ComposerSubmitPayload } from '../components/ComposerPane'
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

const STREAM_BATCH_FALLBACK_FLUSH_MS = 16
const STREAM_BATCH_PRIORITY_FLUSH_MS = 8
const STREAM_BATCH_MAX_QUEUE_AGE_MS = 25
const STREAM_CHUNKING_SMOOTH_DRAIN_MAX_EVENTS = 32
const STREAM_CHUNKING_CATCH_UP_DRAIN_MAX_EVENTS = 128
const STREAM_CHUNKING_ENTER_QUEUE_DEPTH = 64
const STREAM_CHUNKING_ENTER_OLDEST_AGE_MS = 120
const STREAM_CHUNKING_EXIT_QUEUE_DEPTH = 16
const STREAM_CHUNKING_EXIT_OLDEST_AGE_MS = 40
const STREAM_CHUNKING_EXIT_HOLD_MS = 250
const STREAM_CHUNKING_REENTER_HOLD_MS = 250
const STREAM_CHUNKING_SEVERE_QUEUE_DEPTH = 256
const STREAM_CHUNKING_SEVERE_OLDEST_AGE_MS = 320

const STREAM_FORCE_FLUSH_METHODS = new Set<string>([
  'turn/completed',
  'item/completed',
  'error',
  'thread/closed',
  'serverRequest/resolved',
])

const STREAM_DELTA_METHODS = new Set<string>([
  'item/agentMessage/delta',
  'item/plan/delta',
  'item/reasoning/summaryTextDelta',
  'item/reasoning/summaryPartAdded',
  'item/reasoning/textDelta',
  'item/commandExecution/outputDelta',
  'item/fileChange/outputDelta',
])

type ComposerModelOption = {
  value: string
  label: string
  isDefault: boolean
}

const FULL_ACCESS_APPROVAL_POLICY = 'never'
const FULL_ACCESS_SANDBOX_POLICY: Record<string, unknown> = { type: 'dangerFullAccess' }

function parseTimestampMs(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Date.parse(value)
    if (Number.isFinite(parsed)) {
      return parsed
    }
  }
  return 0
}

function normalizeModelOption(entry: SessionModelEntryV2): ComposerModelOption | null {
  const model = typeof entry.model === 'string' ? entry.model.trim() : ''
  if (!model) {
    return null
  }
  const displayName = typeof entry.displayName === 'string' ? entry.displayName.trim() : ''
  return {
    value: model,
    label: displayName || model,
    isDefault: Boolean(entry.isDefault),
  }
}

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

function isDeltaEnvelope(envelope: SessionEventEnvelope): boolean {
  return STREAM_DELTA_METHODS.has(envelope.method)
}

function shouldForceFlushEnvelope(envelope: SessionEventEnvelope): boolean {
  return STREAM_FORCE_FLUSH_METHODS.has(envelope.method)
}

export function SessionConsoleV2() {
  const [runtimeError, setRuntimeError] = useState<string | null>(null)
  const [isBootstrapping, setIsBootstrapping] = useState(false)
  const reconnectTimerRef = useRef<number | null>(null)
  const pollTimerRef = useRef<number | null>(null)
  const eventSourceRef = useRef<EventSource | null>(null)
  const clearStreamBufferRef = useRef<(() => void) | null>(null)
  const selectionIntentRef = useRef(0)
  const hydratedThreadIdsRef = useRef<Set<string>>(new Set())
  const [isModelLoading, setIsModelLoading] = useState(false)
  const [modelOptions, setModelOptions] = useState<ComposerModelOption[]>([])
  const [selectedModelByThread, setSelectedModelByThread] = useState<Record<string, string>>({})

  const {
    threadsById,
    threadOrder,
    turnsByThread,
    itemsByTurn,
    activeThreadId,
    gapDetectedByThread,
    setThreadList,
    upsertThread,
    markThreadActivity,
    setActiveThreadId,
    setThreadTurns,
    applyEventsBatch,
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
      gapDetectedByThread: state.gapDetectedByThread,
      setThreadList: state.setThreadList,
      upsertThread: state.upsertThread,
      markThreadActivity: state.markThreadActivity,
      setActiveThreadId: state.setActiveThreadId,
      setThreadTurns: state.setThreadTurns,
      applyEventsBatch: state.applyEventsBatch,
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
    () => {
      const indexById = new Map<string, number>()
      threadOrder.forEach((threadId, index) => {
        indexById.set(threadId, index)
      })
      return threadOrder
        .map((threadId) => threadsById[threadId])
        .filter((thread): thread is NonNullable<typeof thread> => Boolean(thread))
        .sort((left, right) => {
          const diff = parseTimestampMs(right.updatedAt) - parseTimestampMs(left.updatedAt)
          if (diff !== 0) {
            return diff
          }
          return (indexById.get(left.id) ?? 0) - (indexById.get(right.id) ?? 0)
        })
    },
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

  const selectedModel = useMemo(() => {
    if (!activeThreadId) {
      return null
    }
    const chosen = selectedModelByThread[activeThreadId]
    if (typeof chosen === 'string' && chosen.trim().length > 0) {
      return chosen
    }
    const threadModel = typeof activeThread?.model === 'string' ? activeThread.model.trim() : ''
    if (threadModel) {
      return threadModel
    }
    return modelOptions.find((option) => option.isDefault)?.value ?? modelOptions[0]?.value ?? null
  }, [activeThread?.model, activeThreadId, modelOptions, selectedModelByThread])

  const closeStream = useCallback((threadId: string | null) => {
    const clearBuffer = clearStreamBufferRef.current
    if (clearBuffer) {
      clearBuffer()
      clearStreamBufferRef.current = null
    }
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

  const hydrateThreadState = useCallback(async (threadId: string, options?: { force?: boolean }) => {
    if (!options?.force && hydratedThreadIdsRef.current.has(threadId)) {
      return
    }
    const read = await readThreadV2(threadId, false)
    upsertThread(read.thread, { preserveUpdatedAt: true })
    const turns = await listThreadTurnsV2(threadId, { limit: 200 })
    setThreadTurns(threadId, turns.data)
    hydratedThreadIdsRef.current.add(threadId)
  }, [setThreadTurns, upsertThread])

  const ensureThreadReady = useCallback(async (threadId: string, options?: { forceHydrate?: boolean }) => {
    const snapshot = useThreadSessionStore.getState()
    const cachedThread = snapshot.threadsById[threadId]
    const needsResume = !cachedThread || cachedThread.status?.type === 'notLoaded'
    if (needsResume) {
      const resumed = await resumeThreadV2(threadId, {})
      upsertThread(resumed.thread, { preserveUpdatedAt: true })
    }
    await hydrateThreadState(threadId, { force: Boolean(options?.forceHydrate) })
  }, [hydrateThreadState, upsertThread])

  const openStream = useCallback((threadId: string) => {
    closeStream(threadId)
    clearGapDetected(threadId)
    const cursorEventId = useThreadSessionStore.getState().lastEventIdByThread[threadId] ?? null
    const stream = openThreadEventsStreamV2(threadId, { cursorEventId })
    eventSourceRef.current = stream
    type FlushReason = 'raf' | 'fallback' | 'forced' | 'max_age'
    type StreamChunkingMode = 'smooth' | 'catch_up'
    const queuedEnvelopes: SessionEventEnvelope[] = []
    let queuedSinceMs: number | null = null
    let rafFlushHandle: number | null = null
    let fallbackFlushTimer: ReturnType<typeof globalThis.setTimeout> | null = null
    let maxAgeFlushTimer: ReturnType<typeof globalThis.setTimeout> | null = null
    let streamChunkingMode: StreamChunkingMode = 'smooth'
    let streamChunkingBelowExitThresholdSinceMs: number | null = null
    let streamChunkingLastCatchUpExitAtMs: number | null = null

    const resetStreamChunkingMode = () => {
      streamChunkingMode = 'smooth'
      streamChunkingBelowExitThresholdSinceMs = null
      streamChunkingLastCatchUpExitAtMs = null
    }

    const clearScheduledFlush = () => {
      if (rafFlushHandle !== null && typeof globalThis.cancelAnimationFrame === 'function') {
        globalThis.cancelAnimationFrame(rafFlushHandle)
      }
      rafFlushHandle = null
      if (fallbackFlushTimer !== null) {
        globalThis.clearTimeout(fallbackFlushTimer)
      }
      fallbackFlushTimer = null
      if (maxAgeFlushTimer !== null) {
        globalThis.clearTimeout(maxAgeFlushTimer)
      }
      maxAgeFlushTimer = null
    }

    const clearQueuedEnvelopes = () => {
      queuedEnvelopes.length = 0
      queuedSinceMs = null
      resetStreamChunkingMode()
      clearScheduledFlush()
    }

    clearStreamBufferRef.current = clearQueuedEnvelopes

    const resolveStreamChunkingMode = (
      queuedCount: number,
      oldestAgeMs: number,
      nowMs: number,
    ): StreamChunkingMode => {
      if (queuedCount <= 0) {
        resetStreamChunkingMode()
        return streamChunkingMode
      }

      const shouldEnterCatchUp =
        queuedCount >= STREAM_CHUNKING_ENTER_QUEUE_DEPTH ||
        oldestAgeMs >= STREAM_CHUNKING_ENTER_OLDEST_AGE_MS
      const shouldExitCatchUp =
        queuedCount <= STREAM_CHUNKING_EXIT_QUEUE_DEPTH &&
        oldestAgeMs <= STREAM_CHUNKING_EXIT_OLDEST_AGE_MS
      const severeBacklog =
        queuedCount >= STREAM_CHUNKING_SEVERE_QUEUE_DEPTH ||
        oldestAgeMs >= STREAM_CHUNKING_SEVERE_OLDEST_AGE_MS
      const reentryHoldActive =
        streamChunkingLastCatchUpExitAtMs != null &&
        nowMs - streamChunkingLastCatchUpExitAtMs < STREAM_CHUNKING_REENTER_HOLD_MS

      if (streamChunkingMode === 'smooth') {
        if (shouldEnterCatchUp && (!reentryHoldActive || severeBacklog)) {
          streamChunkingMode = 'catch_up'
          streamChunkingBelowExitThresholdSinceMs = null
          streamChunkingLastCatchUpExitAtMs = null
        }
        return streamChunkingMode
      }

      if (!shouldExitCatchUp) {
        streamChunkingBelowExitThresholdSinceMs = null
        return streamChunkingMode
      }

      if (streamChunkingBelowExitThresholdSinceMs == null) {
        streamChunkingBelowExitThresholdSinceMs = nowMs
        return streamChunkingMode
      }

      if (nowMs - streamChunkingBelowExitThresholdSinceMs >= STREAM_CHUNKING_EXIT_HOLD_MS) {
        streamChunkingMode = 'smooth'
        streamChunkingBelowExitThresholdSinceMs = null
        streamChunkingLastCatchUpExitAtMs = nowMs
      }

      return streamChunkingMode
    }

    const scheduleQueuedFlush = (priority = false) => {
      if (rafFlushHandle === null && typeof globalThis.requestAnimationFrame === 'function') {
        rafFlushHandle = globalThis.requestAnimationFrame(() => {
          rafFlushHandle = null
          flushQueuedEnvelopes('raf')
        })
      }
      const fallbackDelayMs = priority
        ? Math.min(STREAM_BATCH_FALLBACK_FLUSH_MS, STREAM_BATCH_PRIORITY_FLUSH_MS)
        : STREAM_BATCH_FALLBACK_FLUSH_MS
      if (fallbackFlushTimer === null) {
        fallbackFlushTimer = globalThis.setTimeout(() => {
          fallbackFlushTimer = null
          flushQueuedEnvelopes('fallback')
        }, fallbackDelayMs)
      }
      if (maxAgeFlushTimer === null && queuedSinceMs !== null) {
        const ageMs = Math.max(0, Date.now() - queuedSinceMs)
        const maxAgeTargetMs = priority
          ? Math.min(STREAM_BATCH_MAX_QUEUE_AGE_MS, STREAM_BATCH_PRIORITY_FLUSH_MS)
          : STREAM_BATCH_MAX_QUEUE_AGE_MS
        const waitMs = Math.max(0, maxAgeTargetMs - ageMs)
        maxAgeFlushTimer = globalThis.setTimeout(() => {
          maxAgeFlushTimer = null
          flushQueuedEnvelopes('max_age')
        }, waitMs)
      }
    }

    const flushQueuedEnvelopes = (reason: FlushReason) => {
      if (queuedEnvelopes.length === 0) {
        return
      }

      clearScheduledFlush()
      const nowMs = Date.now()
      const oldestQueueAgeMs = queuedSinceMs == null ? 0 : Math.max(0, nowMs - queuedSinceMs)
      const mode = resolveStreamChunkingMode(queuedEnvelopes.length, oldestQueueAgeMs, nowMs)
      const maxEventsPerFlush =
        reason === 'forced' || reason === 'max_age'
          ? queuedEnvelopes.length
          : mode === 'catch_up'
            ? STREAM_CHUNKING_CATCH_UP_DRAIN_MAX_EVENTS
            : STREAM_CHUNKING_SMOOTH_DRAIN_MAX_EVENTS
      const drainCount = Math.max(1, Math.min(queuedEnvelopes.length, maxEventsPerFlush))
      const envelopes = queuedEnvelopes.splice(0, drainCount)
      if (queuedEnvelopes.length === 0) {
        queuedSinceMs = null
        resetStreamChunkingMode()
      }

      applyEventsBatch(envelopes)
      const state = useThreadSessionStore.getState()
      if (state.gapDetectedByThread[threadId]) {
        clearGapDetected(threadId)
        clearQueuedEnvelopes()
        closeStream(threadId)
        openStream(threadId)
        return
      }

      if (queuedEnvelopes.length > 0) {
        const nextEnvelope = queuedEnvelopes[0]
        const priorityFlush = nextEnvelope != null && isDeltaEnvelope(nextEnvelope)
        scheduleQueuedFlush(priorityFlush)
      }
    }

    const enqueueEnvelope = (envelope: SessionEventEnvelope) => {
      if (queuedEnvelopes.length === 0) {
        queuedSinceMs = Date.now()
      }
      queuedEnvelopes.push(envelope)
      if (shouldForceFlushEnvelope(envelope)) {
        flushQueuedEnvelopes('forced')
        return
      }
      const priorityFlush = isDeltaEnvelope(envelope)
      scheduleQueuedFlush(priorityFlush)
    }

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
      clearQueuedEnvelopes()
      reconnectTimerRef.current = window.setTimeout(() => {
        openStream(threadId)
      }, 1000)
    }

    const handler = (event: MessageEvent) => {
      const parsed = parseSessionEvent(event.data)
      if (!parsed) {
        return
      }
      enqueueEnvelope(parsed)
    }

    for (const method of EVENT_METHODS) {
      stream.addEventListener(method, handler as EventListener)
    }
  }, [
    applyEventsBatch,
    closeStream,
    clearGapDetected,
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

  const loadModels = useCallback(async () => {
    setIsModelLoading(true)
    try {
      let cursor: string | null = null
      const nextOptions: ComposerModelOption[] = []
      const seen = new Set<string>()

      for (let page = 0; page < 5; page += 1) {
        const listed = await listModelsV2({
          cursor,
          limit: 100,
          includeHidden: false,
        })
        for (const entry of listed.data) {
          const normalized = normalizeModelOption(entry)
          if (!normalized || seen.has(normalized.value)) {
            continue
          }
          seen.add(normalized.value)
          nextOptions.push(normalized)
        }
        if (!listed.nextCursor) {
          break
        }
        cursor = listed.nextCursor
      }

      nextOptions.sort((left, right) => {
        if (left.isDefault !== right.isDefault) {
          return left.isDefault ? -1 : 1
        }
        return left.label.localeCompare(right.label)
      })
      setModelOptions(nextOptions)
    } catch {
      setModelOptions([])
    } finally {
      setIsModelLoading(false)
    }
  }, [])

  const bootstrap = useCallback(async () => {
    setIsBootstrapping(true)
    setPhase('connecting')
    try {
      const initialized = await initializeSessionV2()
      setInitialized(
        initialized.connection.clientName ?? 'PlanningTree Session V2',
        initialized.connection.serverVersion ?? null,
      )
      void loadModels()

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
  }, [ensureThreadReady, loadModels, setActiveThreadId, setError, setInitialized, setPhase, setThreadList, upsertThread])

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
      hydratedThreadIdsRef.current.clear()
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

  useEffect(() => {
    if (!activeThreadId || !selectedModel) {
      return
    }
    setSelectedModelByThread((previous) => {
      if (previous[activeThreadId]) {
        return previous
      }
      return { ...previous, [activeThreadId]: selectedModel }
    })
  }, [activeThreadId, selectedModel])

  const handleSelectThread = useCallback(async (threadId: string) => {
    const snapshot = useThreadSessionStore.getState()
    if (snapshot.activeThreadId === threadId) {
      setRuntimeError(null)
      return
    }

    const cachedThread = snapshot.threadsById[threadId]
    if (hydratedThreadIdsRef.current.has(threadId) && cachedThread?.status?.type !== 'notLoaded') {
      setActiveThreadId(threadId)
      setRuntimeError(null)
      return
    }

    const selectionIntent = selectionIntentRef.current + 1
    selectionIntentRef.current = selectionIntent
    try {
      await ensureThreadReady(threadId)
      if (selectionIntentRef.current !== selectionIntent) {
        return
      }
      setActiveThreadId(threadId)
      setRuntimeError(null)
    } catch (error) {
      if (selectionIntentRef.current !== selectionIntent) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [ensureThreadReady, setActiveThreadId])

  const handleCreateThread = useCallback(async () => {
    const selectionIntent = selectionIntentRef.current + 1
    selectionIntentRef.current = selectionIntent
    try {
      const created = await startThreadV2({ modelProvider: 'openai' })
      upsertThread(created.thread)
      await ensureThreadReady(created.thread.id)
      if (selectionIntentRef.current !== selectionIntent) {
        return
      }
      setActiveThreadId(created.thread.id)
      setRuntimeError(null)
    } catch (error) {
      if (selectionIntentRef.current !== selectionIntent) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [ensureThreadReady, setActiveThreadId, upsertThread])

  const handleForkThread = useCallback(async (threadId: string) => {
    const selectionIntent = selectionIntentRef.current + 1
    selectionIntentRef.current = selectionIntent
    try {
      const forked = await forkThreadV2(threadId, {})
      upsertThread(forked.thread)
      await ensureThreadReady(forked.thread.id)
      if (selectionIntentRef.current !== selectionIntent) {
        return
      }
      setActiveThreadId(forked.thread.id)
      setRuntimeError(null)
    } catch (error) {
      if (selectionIntentRef.current !== selectionIntent) {
        return
      }
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [ensureThreadReady, setActiveThreadId, upsertThread])

  const handleRefresh = useCallback(async () => {
    try {
      const listed = await listThreadsV2({ limit: 50 })
      setThreadList(listed.data)
      if (activeThreadId) {
        await hydrateThreadState(activeThreadId, { force: true })
      }
      setRuntimeError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [activeThreadId, hydrateThreadState, setThreadList])

  const handleModelChange = useCallback((model: string) => {
    if (!activeThreadId) {
      return
    }
    setSelectedModelByThread((previous) => ({
      ...previous,
      [activeThreadId]: model,
    }))
  }, [activeThreadId])

  const handleSubmit = useCallback(async (payload: ComposerSubmitPayload) => {
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
        markThreadActivity(activeThreadId)
      } else {
        const permissionOverrides = payload.accessMode === 'full-access'
          ? { approvalPolicy: FULL_ACCESS_APPROVAL_POLICY, sandboxPolicy: FULL_ACCESS_SANDBOX_POLICY }
          : {}
        const result = await startTurnV2(activeThreadId, {
          clientActionId: actionId(),
          input: payload.input,
          model: payload.model ?? selectedModel,
          ...permissionOverrides,
        })
        const nextTurns = upsertTurnList(activeTurns, result.turn)
        setThreadTurns(activeThreadId, nextTurns)
        markThreadActivity(activeThreadId)
      }
      setRuntimeError(null)
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error)
      setRuntimeError(message)
    }
  }, [activeRunningTurn, activeThreadId, activeTurns, markThreadActivity, selectedModel, setThreadTurns])

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
          modelOptions={modelOptions}
          selectedModel={selectedModel}
          onModelChange={handleModelChange}
          isModelLoading={isModelLoading}
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
