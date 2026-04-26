import { unstable_batchedUpdates } from 'react-dom'
import { openThreadEventsStreamV2 } from '../api/client'
import type { SessionEventEnvelope, SessionNotificationMethod } from '../contracts'
import { parseSessionEvent } from '../state/sessionEventParser'

const EVENT_METHODS: SessionNotificationMethod[] = [
  'thread/started',
  'thread/status/changed',
  'thread/closed',
  'thread/archived',
  'thread/unarchived',
  'thread/name/updated',
  'thread/tokenUsage/updated',
  'thread/compacted',
  'turn/started',
  'turn/completed',
  'turn/failed',
  'turn/diff/updated',
  'turn/plan/updated',
  'task/started',
  'task/completed',
  'task/failed',
  'item/started',
  'item/completed',
  'item/autoApprovalReview/started',
  'item/autoApprovalReview/completed',
  'item/agentMessage/delta',
  'item/plan/delta',
  'item/mcpToolCall/progress',
  'item/reasoning/summaryTextDelta',
  'item/reasoning/summaryPartAdded',
  'item/reasoning/textDelta',
  'item/commandExecution/outputDelta',
  'item/commandExecution/terminalInteraction',
  'item/fileChange/outputDelta',
  'rawResponseItem/completed',
  'hook/started',
  'hook/completed',
  'thread/realtime/started',
  'thread/realtime/itemAdded',
  'thread/realtime/transcript/delta',
  'thread/realtime/transcript/done',
  'thread/realtime/outputAudio/delta',
  'thread/realtime/sdp',
  'thread/realtime/error',
  'thread/realtime/closed',
  'serverRequest/created',
  'serverRequest/updated',
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
  'turn/failed',
  'task/completed',
  'task/failed',
  'item/completed',
  'rawResponseItem/completed',
  'error',
  'thread/closed',
  'thread/compacted',
  'turn/diff/updated',
  'turn/plan/updated',
  'item/autoApprovalReview/completed',
  'item/mcpToolCall/progress',
  'hook/completed',
  'thread/realtime/error',
  'thread/realtime/closed',
  'serverRequest/created',
  'serverRequest/updated',
  'serverRequest/resolved',
])

const STREAM_DELTA_METHODS = new Set<string>([
  'item/agentMessage/delta',
  'item/plan/delta',
  'item/mcpToolCall/progress',
  'item/reasoning/summaryTextDelta',
  'item/reasoning/summaryPartAdded',
  'item/reasoning/textDelta',
  'item/commandExecution/outputDelta',
  'item/commandExecution/terminalInteraction',
  'item/fileChange/outputDelta',
  'thread/realtime/transcript/delta',
  'thread/realtime/outputAudio/delta',
])

const STREAM_TRACE_METHODS = new Set<string>([
  'thread/started',
  'thread/status/changed',
  'thread/closed',
  'turn/started',
  'turn/completed',
  'turn/failed',
  'task/completed',
  'task/failed',
  'item/started',
  'item/completed',
  'item/commandExecution/terminalInteraction',
  'serverRequest/created',
  'serverRequest/updated',
  'serverRequest/resolved',
  'error',
])

type FlushReason = 'raf' | 'fallback' | 'forced' | 'max_age'
type StreamChunkingMode = 'smooth' | 'catch_up'

function isStreamTraceEnabled(): boolean {
  if (typeof window === 'undefined') {
    return false
  }
  try {
    if (window.location.search.includes('debugSession=1')) {
      return true
    }
    return window.localStorage.getItem('sessionV2Trace') === '1'
  } catch {
    return false
  }
}

function traceStream(message: string, payload?: Record<string, unknown>): void {
  if (!isStreamTraceEnabled()) {
    return
  }
  if (payload) {
    console.info(`[session-v2-stream] ${message}`, payload)
    return
  }
  console.info(`[session-v2-stream] ${message}`)
}

export type StreamControllerDependencies = {
  openEventSource?: (threadId: string, options?: { cursorEventId?: string | null }) => EventSource
  applyEventsBatch: (envelopes: SessionEventEnvelope[]) => void
  applyRequestEventsBatch?: (envelopes: SessionEventEnvelope[]) => void
  markStreamConnected: (threadId: string) => void
  markStreamDisconnected: (threadId: string) => void
  markStreamReconnect: (threadId: string) => void
  clearGapDetected: (threadId: string) => void
  getLastEventId: (threadId: string) => string | null
  getGapDetected: (threadId: string) => boolean
  recoverFromGap?: (threadId: string, options: { fullResync: boolean }) => Promise<void> | void
  resetReplayCursor?: (threadId: string) => void
  reportGapMetric?: (payload: {
    threadId: string
    type: 'gap_detected' | 'gap_recovery' | 'gap_repeated'
    count: number
  }) => void
  reportCorrelation?: (payload: {
    type: 'stream_open' | 'stream_connected' | 'stream_error' | 'gap_recovery'
    threadId: string
    cursorEventId?: string | null
    attempt?: number
  }) => void
  onStreamConnected?: (threadId: string) => void
  onRuntimeError?: (message: string | null) => void
}

export type SessionEventStreamController = {
  open: (threadId: string) => void
  close: (threadId?: string | null) => void
  dispose: () => void
}

function isDeltaEnvelope(envelope: SessionEventEnvelope): boolean {
  return STREAM_DELTA_METHODS.has(envelope.method)
}

function shouldForceFlushEnvelope(envelope: SessionEventEnvelope): boolean {
  return STREAM_FORCE_FLUSH_METHODS.has(envelope.method)
}

export function createSessionEventStreamController(
  dependencies: StreamControllerDependencies,
): SessionEventStreamController {
  const openEventSource = dependencies.openEventSource ?? openThreadEventsStreamV2

  let activeThreadId: string | null = null
  let eventSource: EventSource | null = null
  let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null
  let clearBuffer: (() => void) | null = null
  let generation = 0
  let disposed = false
  const gapRecoveryAttemptsByThread = new Map<string, number>()
  const gapRecoveryInFlightByThread = new Set<string>()

  const closeInternal = (options?: { threadId?: string | null; bumpGeneration?: boolean }) => {
    if (options?.bumpGeneration !== false) {
      generation += 1
    }
    const disconnectThreadId = options?.threadId ?? activeThreadId
    const clearPendingBuffer = clearBuffer
    if (clearPendingBuffer) {
      clearPendingBuffer()
      clearBuffer = null
    }
    if (disconnectThreadId) {
      dependencies.markStreamDisconnected(disconnectThreadId)
      traceStream('stream closed', {
        threadId: disconnectThreadId,
        reason: options?.bumpGeneration === false ? 'switch' : 'explicit',
      })
    }
    if (eventSource) {
      eventSource.close()
      eventSource = null
    }
    if (reconnectTimer !== null) {
      globalThis.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    activeThreadId = null
  }

  const scheduleReconnect = (threadId: string, token: number) => {
    if (reconnectTimer !== null) {
      globalThis.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    reconnectTimer = globalThis.setTimeout(() => {
      reconnectTimer = null
      if (disposed || token !== generation) {
        return
      }
      controller.open(threadId)
    }, 1000)
  }

  const controller: SessionEventStreamController = {
    open(threadId) {
      if (disposed) {
        return
      }

      closeInternal({ bumpGeneration: false })
      dependencies.clearGapDetected(threadId)
      traceStream('stream open requested', {
        threadId,
      })

      generation += 1
      const token = generation
      activeThreadId = threadId

      const cursorEventId = dependencies.getLastEventId(threadId)
      traceStream('stream opening', {
        threadId,
        cursorEventId,
      })
      dependencies.reportCorrelation?.({
        type: 'stream_open',
        threadId,
        cursorEventId,
      })
      let stream: EventSource
      try {
        stream = openEventSource(threadId, { cursorEventId })
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error)
        dependencies.markStreamDisconnected(threadId)
        dependencies.markStreamReconnect(threadId)
        dependencies.onRuntimeError?.(message)
        traceStream('stream open failed', {
          threadId,
          message,
        })
        scheduleReconnect(threadId, token)
        return
      }
      eventSource = stream

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

      clearBuffer = clearQueuedEnvelopes

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
        if (token !== generation || disposed || queuedEnvelopes.length === 0) {
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

        unstable_batchedUpdates(() => {
          dependencies.applyEventsBatch(envelopes)
          dependencies.applyRequestEventsBatch?.(envelopes)
        })
        const first = envelopes[0]
        const last = envelopes[envelopes.length - 1]
        if (
          first &&
          last &&
          (STREAM_TRACE_METHODS.has(first.method) || STREAM_TRACE_METHODS.has(last.method) || envelopes.length > 1)
        ) {
          traceStream('stream batch applied', {
            threadId,
            count: envelopes.length,
            firstMethod: first.method,
            firstEventSeq: first.eventSeq,
            lastMethod: last.method,
            lastEventSeq: last.eventSeq,
          })
        }
        if (dependencies.getGapDetected(threadId)) {
          const attempt = (gapRecoveryAttemptsByThread.get(threadId) ?? 0) + 1
          gapRecoveryAttemptsByThread.set(threadId, attempt)
          dependencies.reportGapMetric?.({
            threadId,
            type: 'gap_detected',
            count: attempt,
          })
          traceStream('gap detected', {
            threadId,
            attempt,
          })
          if (attempt > 1) {
            dependencies.reportGapMetric?.({
              threadId,
              type: 'gap_repeated',
              count: attempt,
            })
          }
          clearQueuedEnvelopes()
          if (gapRecoveryInFlightByThread.has(threadId)) {
            return
          }
          gapRecoveryInFlightByThread.add(threadId)
          const shouldFullResync = attempt > 1
          void (async () => {
            controller.close(threadId)
            const reopenGeneration = generation
            let recoveryFailed = false
            try {
              if (shouldFullResync) {
                dependencies.resetReplayCursor?.(threadId)
              }
              dependencies.reportGapMetric?.({
                threadId,
                type: 'gap_recovery',
                count: attempt,
              })
              dependencies.reportCorrelation?.({
                type: 'gap_recovery',
                threadId,
                cursorEventId: dependencies.getLastEventId(threadId),
                attempt,
              })
              traceStream('gap recovery requested', {
                threadId,
                attempt,
                fullResync: shouldFullResync,
              })
              await dependencies.recoverFromGap?.(threadId, { fullResync: shouldFullResync })
            } catch (error) {
              recoveryFailed = true
              const message = error instanceof Error ? error.message : String(error)
              dependencies.onRuntimeError?.(`Session stream gap recovery failed: ${message}`)
              traceStream('gap recovery failed', {
                threadId,
                attempt,
                message,
              })
            } finally {
              gapRecoveryInFlightByThread.delete(threadId)
            }
            if (disposed || reopenGeneration !== generation) {
              return
            }
            dependencies.clearGapDetected(threadId)
            gapRecoveryAttemptsByThread.set(threadId, 0)
            controller.open(threadId)
            if (!recoveryFailed) {
              dependencies.onRuntimeError?.(null)
              traceStream('gap recovery completed', {
                threadId,
                attempt,
                fullResync: shouldFullResync,
              })
            }
          })()
          return
        }

        if (queuedEnvelopes.length > 0) {
          const nextEnvelope = queuedEnvelopes[0]
          const priorityFlush = nextEnvelope != null && isDeltaEnvelope(nextEnvelope)
          scheduleQueuedFlush(priorityFlush)
        }
      }

      const enqueueEnvelope = (envelope: SessionEventEnvelope) => {
        if (token !== generation || disposed) {
          return
        }
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
        if (token !== generation || disposed) {
          return
        }
        dependencies.reportCorrelation?.({
          type: 'stream_connected',
          threadId,
          cursorEventId,
        })
        dependencies.markStreamConnected(threadId)
        dependencies.onRuntimeError?.(null)
        dependencies.onStreamConnected?.(threadId)
        traceStream('stream connected', {
          threadId,
          cursorEventId,
        })
      }

      stream.onerror = () => {
        if (token !== generation || disposed) {
          return
        }
        dependencies.reportCorrelation?.({
          type: 'stream_error',
          threadId,
          cursorEventId,
        })
        dependencies.markStreamDisconnected(threadId)
        dependencies.markStreamReconnect(threadId)
        dependencies.onRuntimeError?.('Session stream disconnected. Reconnecting...')
        clearQueuedEnvelopes()
        traceStream('stream disconnected', {
          threadId,
          cursorEventId,
        })
        scheduleReconnect(threadId, token)
      }

      const handler = (event: MessageEvent) => {
        if (token !== generation || disposed) {
          return
        }
        const rawData = typeof event.data === 'string' ? event.data : String(event.data ?? '')
        const parsed = parseSessionEvent(rawData)
        if (!parsed) {
          const rawPreview = rawData.length > 240 ? `${rawData.slice(0, 240)}...` : rawData
          traceStream('stream event dropped: parse failed', {
            threadId,
            eventType: event.type,
            lastEventId: event.lastEventId ?? null,
            dataLength: rawData.length,
            rawPreview,
          })
          return
        }
        if (STREAM_TRACE_METHODS.has(parsed.method)) {
          traceStream('stream event received', {
            threadId,
            method: parsed.method,
            eventSeq: parsed.eventSeq,
          })
        }
        enqueueEnvelope(parsed)
      }

      for (const method of EVENT_METHODS) {
        stream.addEventListener(method, handler as EventListener)
      }
    },

    close(threadId) {
      closeInternal({ threadId, bumpGeneration: true })
    },

    dispose() {
      disposed = true
      closeInternal({ threadId: activeThreadId, bumpGeneration: true })
    },
  }

  return controller
}
