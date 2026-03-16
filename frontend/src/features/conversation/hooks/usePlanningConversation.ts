import { useEffect, useRef, useState } from 'react'

import { ApiError, api } from '../../../api/client'
import type { PlanningConversationEvent } from '../../../api/types'
import {
  type ConversationScope,
  type ConversationSnapshot,
} from '../types'
import { shouldAcceptConversationEvent } from '../model/applyConversationEvent'
import { useConversationStore, type ConversationViewState } from '../../../stores/conversation-store'

type BootstrapStatus = 'idle' | 'loading_snapshot' | 'error'

type UsePlanningConversationOptions = {
  projectId: string | null
  nodeId: string | null
  enabled: boolean
}

type UsePlanningConversationResult = {
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: BootstrapStatus
  bootstrapError: string | null
  refresh: () => void
}

const MAX_RECONNECT_ATTEMPTS = 5
const RECONNECT_DELAY_MS = [250, 500, 1_000, 2_000, 4_000] as const
const MAX_RECONNECT_DELAY_MS = 5_000
const TERMINAL_STATUSES = new Set(['completed', 'error', 'interrupted', 'cancelled'])

function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function computeReconnectDelayMs(attempt: number): number {
  const baseDelay = RECONNECT_DELAY_MS[Math.min(attempt, RECONNECT_DELAY_MS.length - 1)]
  const jitterFactor = 0.8 + Math.random() * 0.4
  return Math.min(MAX_RECONNECT_DELAY_MS, Math.round(baseDelay * jitterFactor))
}

function flushBufferedEvents(
  conversationId: string,
  bufferedEvents: PlanningConversationEvent[],
) {
  bufferedEvents
    .sort((left, right) => left.event_seq - right.event_seq)
    .forEach((event) => {
      const current = useConversationStore.getState().conversationsById[conversationId]
      if (!current || !shouldAcceptConversationEvent(current.snapshot, event)) {
        return
      }
      useConversationStore.getState().applyEvent(conversationId, event)
    })
  bufferedEvents.length = 0
}

export function usePlanningConversation({
  projectId,
  nodeId,
  enabled,
}: UsePlanningConversationOptions): UsePlanningConversationResult {
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapStatus>('idle')
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)
  const [refreshToken, setRefreshToken] = useState(0)
  const generationRef = useRef(0)
  const lastTerminalRefreshKeyRef = useRef<string | null>(null)
  const scope: ConversationScope | null =
    projectId && nodeId
      ? {
          project_id: projectId,
          node_id: nodeId,
          thread_type: 'planning',
        }
      : null
  const conversationId = useConversationStore((state) =>
    scope ? state.getConversationIdByScope(scope) : null,
  )
  const conversation = useConversationStore((state) =>
    conversationId ? state.conversationsById[conversationId] ?? null : null,
  )

  useEffect(() => {
    lastTerminalRefreshKeyRef.current = null
  }, [enabled, nodeId, projectId])

  useEffect(() => {
    if (!enabled || !projectId || !nodeId) {
      setBootstrapStatus('idle')
      setBootstrapError(null)
      return
    }
    const resolvedProjectId = projectId
    const resolvedNodeId = nodeId
    const generation = generationRef.current + 1
    generationRef.current = generation

    let disposed = false
    let effectConversationId = conversationId
    let isHydrating = false
    let reconnectAttempts = 0
    let bufferedEvents: PlanningConversationEvent[] = []
    let eventSource: EventSource | null = null
    let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null
    let lastReconnectError = 'Planning conversation stream disconnected.'

    function isCurrentGeneration() {
      return !disposed && generationRef.current === generation
    }

    function clearReconnectTimer() {
      if (reconnectTimer !== null) {
        globalThis.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    function closeStream() {
      eventSource?.close()
      eventSource = null
    }

    function markConversationDisconnected() {
      if (!effectConversationId) {
        return
      }
      const store = useConversationStore.getState()
      store.setConnectionStatus(effectConversationId, 'disconnected')
      store.setLoading(effectConversationId, false)
    }

    async function hydrateSnapshot(
      connectionStatus: 'connecting' | 'reconnecting',
    ): Promise<{ conversationId: string; snapshot: ConversationSnapshot } | null> {
      const store = useConversationStore.getState()
      isHydrating = true
      bufferedEvents = []
      if (effectConversationId) {
        store.setLoading(effectConversationId, true)
        store.setError(effectConversationId, null)
        store.setConnectionStatus(
          effectConversationId,
          connectionStatus === 'connecting' ? 'loading_snapshot' : 'reconnecting',
        )
      } else {
        setBootstrapStatus('loading_snapshot')
        setBootstrapError(null)
      }

      try {
        const response = await api.getPlanningConversation(resolvedProjectId, resolvedNodeId)
        if (!isCurrentGeneration()) {
          return null
        }
        const snapshot = response.conversation
        const nextConversationId = store.ensureConversation(snapshot)
        store.hydrateConversation(snapshot)
        store.setLoading(nextConversationId, false)
        store.setError(nextConversationId, null)
        store.setConnectionStatus(nextConversationId, 'connecting')
        effectConversationId = nextConversationId
        setBootstrapStatus('idle')
        setBootstrapError(null)
        return { conversationId: nextConversationId, snapshot }
      } catch (error) {
        if (!isCurrentGeneration()) {
          return null
        }
        const message = toErrorMessage(error)
        if (connectionStatus === 'reconnecting') {
          if (effectConversationId) {
            store.setLoading(effectConversationId, false)
            store.setConnectionStatus(effectConversationId, 'reconnecting')
          }
          lastReconnectError = message
          return null
        }
        if (effectConversationId) {
          store.setLoading(effectConversationId, false)
          store.setConnectionStatus(effectConversationId, 'error')
          store.setError(effectConversationId, message)
        } else {
          setBootstrapStatus('error')
          setBootstrapError(message)
        }
        return null
      } finally {
        isHydrating = false
      }
    }

    function finalizeReconnectExhaustion() {
      if (!effectConversationId) {
        setBootstrapStatus('error')
        setBootstrapError(lastReconnectError)
        return
      }
      const store = useConversationStore.getState()
      store.setLoading(effectConversationId, false)
      store.setConnectionStatus(effectConversationId, 'error')
      store.setError(effectConversationId, lastReconnectError, 'reconnect_exhausted')
    }

    function scheduleTerminalRefresh(event: PlanningConversationEvent) {
      const refreshKey = `${event.stream_id}:${event.event_seq}`
      if (lastTerminalRefreshKeyRef.current === refreshKey) {
        return
      }
      lastTerminalRefreshKeyRef.current = refreshKey
      setRefreshToken((current) => current + 1)
    }

    function openStream(snapshot: ConversationSnapshot) {
      const nextConversationId = effectConversationId
      if (!nextConversationId || !isCurrentGeneration()) {
        return
      }
      clearReconnectTimer()
      closeStream()
      eventSource = new EventSource(
        api.planningConversationEventsUrl(resolvedProjectId, resolvedNodeId, {
          afterEventSeq: snapshot.record.event_seq,
          expectedStreamId: snapshot.record.active_stream_id,
        }),
      )

      eventSource.onopen = () => {
        if (!isCurrentGeneration()) {
          return
        }
        reconnectAttempts = 0
        useConversationStore.getState().setConnectionStatus(nextConversationId, 'connected')
        useConversationStore.getState().setError(nextConversationId, null)
      }

      eventSource.onmessage = (message) => {
        if (!isCurrentGeneration()) {
          return
        }
        try {
          const event = JSON.parse(message.data) as PlanningConversationEvent
          if (event.conversation_id !== nextConversationId) {
            return
          }
          if (isHydrating) {
            bufferedEvents.push(event)
            return
          }
          const current = useConversationStore.getState().conversationsById[nextConversationId]
          if (!current || !shouldAcceptConversationEvent(current.snapshot, event)) {
            return
          }
          useConversationStore.getState().applyEvent(nextConversationId, event)
          if (
            event.event_type === 'completion_status' &&
            TERMINAL_STATUSES.has(String(event.payload.status ?? ''))
          ) {
            scheduleTerminalRefresh(event)
          }
        } catch {
          return
        }
      }

      eventSource.onerror = () => {
        if (!isCurrentGeneration()) {
          return
        }
        closeStream()
        scheduleReconnect('Planning conversation stream disconnected.')
      }
    }

    async function reconnect() {
      if (!isCurrentGeneration()) {
        return
      }
      const refreshed = await hydrateSnapshot('reconnecting')
      if (!isCurrentGeneration()) {
        return
      }
      if (!refreshed) {
        scheduleReconnect(lastReconnectError)
        return
      }
      flushBufferedEvents(refreshed.conversationId, bufferedEvents)
      openStream(refreshed.snapshot)
    }

    function scheduleReconnect(message: string) {
      if (!isCurrentGeneration()) {
        return
      }
      lastReconnectError = message
      clearReconnectTimer()
      if (effectConversationId) {
        const store = useConversationStore.getState()
        store.setLoading(effectConversationId, false)
        store.setConnectionStatus(effectConversationId, 'reconnecting')
        store.setError(effectConversationId, null)
      }
      if (reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
        finalizeReconnectExhaustion()
        return
      }
      const delayMs = computeReconnectDelayMs(reconnectAttempts)
      reconnectAttempts += 1
      reconnectTimer = globalThis.setTimeout(() => {
        if (!isCurrentGeneration()) {
          return
        }
        void reconnect()
      }, delayMs)
    }

    void (async () => {
      const initial = await hydrateSnapshot('connecting')
      if (!isCurrentGeneration() || !initial) {
        return
      }
      flushBufferedEvents(initial.conversationId, bufferedEvents)
      openStream(initial.snapshot)
    })()

    return () => {
      disposed = true
      if (generationRef.current === generation) {
        generationRef.current += 1
      }
      clearReconnectTimer()
      closeStream()
      markConversationDisconnected()
    }
  }, [enabled, nodeId, projectId, refreshToken])

  function refresh() {
    setRefreshToken((current) => current + 1)
  }

  return {
    conversationId,
    conversation,
    bootstrapStatus,
    bootstrapError,
    refresh,
  }
}
