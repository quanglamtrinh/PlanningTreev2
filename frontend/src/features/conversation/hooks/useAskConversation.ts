import { useEffect, useRef, useState } from 'react'

import { ApiError, api } from '../../../api/client'
import type {
  AskConversationEvent,
  AskConversationSendAcceptedResponse,
} from '../../../api/types'
import {
  createConversationScopeKey,
  type ConversationScope,
  type ConversationSnapshot,
} from '../types'
import { useConversationStore, type ConversationViewState } from '../../../stores/conversation-store'
import {
  applyIncomingConversationEvent,
  flushBufferedConversationEvents,
  getAuthoritativeConversationSnapshot,
} from './streamRuntime'

type BootstrapStatus = 'idle' | 'loading_snapshot' | 'error'

type UseAskConversationOptions = {
  projectId: string | null
  nodeId: string | null
  enabled: boolean
}

type UseAskConversationResult = {
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: BootstrapStatus
  bootstrapError: string | null
  send: (content: string) => Promise<AskConversationSendAcceptedResponse | void>
  refresh: () => void
}

const MAX_RECONNECT_ATTEMPTS = 5
const RECONNECT_DELAY_MS = [250, 500, 1_000, 2_000, 4_000] as const
const MAX_RECONNECT_DELAY_MS = 5_000

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

export function useAskConversation({
  projectId,
  nodeId,
  enabled,
}: UseAskConversationOptions): UseAskConversationResult {
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapStatus>('idle')
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)
  const [refreshToken, setRefreshToken] = useState(0)
  const generationRef = useRef(0)
  const sendAttemptRef = useRef(0)
  const conversationIdRef = useRef<string | null>(null)
  const scope: ConversationScope | null =
    projectId && nodeId
      ? {
          project_id: projectId,
          node_id: nodeId,
          thread_type: 'ask',
        }
      : null
  const scopeKey = scope ? createConversationScopeKey(scope) : null
  const scopeKeyRef = useRef<string | null>(scopeKey)
  scopeKeyRef.current = scopeKey
  const conversationId = useConversationStore((state) =>
    scope ? state.getConversationIdByScope(scope) : null,
  )
  const conversation = useConversationStore((state) =>
    conversationId ? state.conversationsById[conversationId] ?? null : null,
  )

  useEffect(() => {
    conversationIdRef.current = conversationId
  }, [conversationId])

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
    let bufferedEvents: AskConversationEvent[] = []
    let eventSource: EventSource | null = null
    let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null
    let lastReconnectError = 'Ask conversation stream disconnected.'

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
      store.setSending(effectConversationId, false)
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
        const response = await api.getAskConversation(resolvedProjectId, resolvedNodeId)
        if (!isCurrentGeneration()) {
          return null
        }
        const snapshot = response.conversation
        const nextConversationId = store.ensureConversation(snapshot)
        store.hydrateConversation(snapshot)
        const authoritativeSnapshot = getAuthoritativeConversationSnapshot(nextConversationId, snapshot)
        store.setLoading(nextConversationId, false)
        store.setError(nextConversationId, null)
        store.setConnectionStatus(nextConversationId, 'connecting')
        effectConversationId = nextConversationId
        conversationIdRef.current = nextConversationId
        setBootstrapStatus('idle')
        setBootstrapError(null)
        return { conversationId: nextConversationId, snapshot: authoritativeSnapshot }
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

    function openStream(snapshot: ConversationSnapshot) {
      const nextConversationId = effectConversationId
      if (!nextConversationId || !isCurrentGeneration()) {
        return
      }
      clearReconnectTimer()
      closeStream()
      eventSource = new EventSource(
        api.askConversationEventsUrl(resolvedProjectId, resolvedNodeId, {
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
          const event = JSON.parse(message.data) as AskConversationEvent
          if (event.conversation_id !== nextConversationId) {
            return
          }
          if (isHydrating) {
            bufferedEvents.push(event)
            return
          }
          const result = applyIncomingConversationEvent(nextConversationId, event)
          if (result.decision === 'recover') {
            closeStream()
            scheduleReconnect('Ask conversation stream lost event continuity.')
            return
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
        scheduleReconnect('Ask conversation stream disconnected.')
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
      const flushed = flushBufferedConversationEvents(refreshed.conversationId, bufferedEvents)
      openStream(flushed.latestSnapshot ?? refreshed.snapshot)
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
      const flushed = flushBufferedConversationEvents(initial.conversationId, bufferedEvents)
      openStream(flushed.latestSnapshot ?? initial.snapshot)
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

  async function send(content: string): Promise<AskConversationSendAcceptedResponse | void> {
    const text = content.trim()
    if (!text || !projectId || !nodeId || !scopeKey) {
      return
    }
    const currentConversationId = conversationIdRef.current
    if (!currentConversationId) {
      throw new Error('Ask conversation is not ready yet.')
    }
    const currentGeneration = generationRef.current
    const sendAttemptId = sendAttemptRef.current + 1
    sendAttemptRef.current = sendAttemptId
    const store = useConversationStore.getState()
    store.setSending(currentConversationId, true)
    store.setError(currentConversationId, null)
    try {
      const response = await api.sendAskConversationMessage(projectId, nodeId, text)
      const requestStillCurrent =
        generationRef.current === currentGeneration &&
        sendAttemptRef.current === sendAttemptId &&
        scopeKeyRef.current === scopeKey

      if (requestStillCurrent && conversationIdRef.current === response.conversation_id) {
        const current = useConversationStore.getState().conversationsById[response.conversation_id]
        const activeStreamId = current?.snapshot.record.active_stream_id ?? null
        if (!activeStreamId || activeStreamId === response.stream_id) {
          store.patchRecord(response.conversation_id, {
            active_stream_id: response.stream_id,
            status: 'active',
          })
        }
        store.setSending(response.conversation_id, false)
        store.setError(response.conversation_id, null)
      }
      return response
    } catch (error) {
      const requestStillCurrent =
        generationRef.current === currentGeneration &&
        sendAttemptRef.current === sendAttemptId &&
        scopeKeyRef.current === scopeKey &&
        conversationIdRef.current === currentConversationId
      if (requestStillCurrent) {
        store.setSending(currentConversationId, false)
        store.setError(currentConversationId, toErrorMessage(error), 'send')
      }
      throw error
    }
  }

  function refresh() {
    setRefreshToken((current) => current + 1)
  }

  return {
    conversationId,
    conversation,
    bootstrapStatus,
    bootstrapError,
    send,
    refresh,
  }
}
