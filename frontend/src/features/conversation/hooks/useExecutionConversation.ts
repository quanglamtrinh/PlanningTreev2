import { useEffect, useRef, useState } from 'react'

import { ApiError, api } from '../../../api/client'
import type {
  ExecutionConversationEvent,
  ExecutionConversationSendAcceptedResponse,
} from '../../../api/types'
import type { ConversationScope, ConversationSnapshot } from '../types'
import { useConversationStore, type ConversationViewState } from '../../../stores/conversation-store'

type BootstrapStatus = 'idle' | 'loading_snapshot' | 'error'

type UseExecutionConversationOptions = {
  projectId: string | null
  nodeId: string | null
  enabled: boolean
}

type UseExecutionConversationResult = {
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: BootstrapStatus
  bootstrapError: string | null
  send: (content: string) => Promise<ExecutionConversationSendAcceptedResponse | void>
}

function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function flushBufferedEvents(
  conversationId: string,
  snapshot: ConversationSnapshot,
  bufferedEvents: ExecutionConversationEvent[],
) {
  const store = useConversationStore.getState()
  bufferedEvents
    .sort((left, right) => left.event_seq - right.event_seq)
    .filter((event) => event.event_seq > snapshot.record.event_seq)
    .forEach((event) => {
      store.applyEvent(conversationId, event)
    })
  bufferedEvents.length = 0
}

export function useExecutionConversation({
  projectId,
  nodeId,
  enabled,
}: UseExecutionConversationOptions): UseExecutionConversationResult {
  const [bootstrapStatus, setBootstrapStatus] = useState<BootstrapStatus>('idle')
  const [bootstrapError, setBootstrapError] = useState<string | null>(null)
  const conversationIdRef = useRef<string | null>(null)
  const scope: ConversationScope | null =
    projectId && nodeId
      ? {
          project_id: projectId,
          node_id: nodeId,
          thread_type: 'execution',
        }
      : null
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

    let disposed = false
    let isHydrating = false
    let bufferedEvents: ExecutionConversationEvent[] = []
    let eventSource: EventSource | null = null

    function closeStream() {
      eventSource?.close()
      eventSource = null
    }

    async function hydrateSnapshot(connectionStatus: 'connecting' | 'reconnecting') {
      const currentConversationId = conversationIdRef.current
      const store = useConversationStore.getState()
      isHydrating = true
      bufferedEvents = []
      if (currentConversationId) {
        store.setLoading(currentConversationId, true)
        store.setError(currentConversationId, null)
        store.setConnectionStatus(
          currentConversationId,
          connectionStatus === 'connecting' ? 'loading_snapshot' : 'reconnecting',
        )
      } else {
        setBootstrapStatus('loading_snapshot')
        setBootstrapError(null)
      }

      try {
        const response = await api.getExecutionConversation(resolvedProjectId, resolvedNodeId)
        if (disposed) {
          return null
        }
        const snapshot = response.conversation
        const nextConversationId = store.ensureConversation(snapshot)
        store.hydrateConversation(snapshot)
        store.setLoading(nextConversationId, false)
        store.setError(nextConversationId, null)
        store.setConnectionStatus(nextConversationId, 'connecting')
        conversationIdRef.current = nextConversationId
        setBootstrapStatus('idle')
        setBootstrapError(null)
        flushBufferedEvents(nextConversationId, snapshot, bufferedEvents)
        return { conversationId: nextConversationId, snapshot }
      } catch (error) {
        if (disposed) {
          return null
        }
        const message = toErrorMessage(error)
        const nextConversationId = conversationIdRef.current
        if (nextConversationId) {
          store.setLoading(nextConversationId, false)
          store.setConnectionStatus(nextConversationId, 'error')
          store.setError(nextConversationId, message)
        } else {
          setBootstrapStatus('error')
          setBootstrapError(message)
        }
        return null
      } finally {
        isHydrating = false
      }
    }

    function openStream(snapshot: ConversationSnapshot) {
      const nextConversationId = conversationIdRef.current
      if (!nextConversationId || disposed) {
        return
      }
      closeStream()
      eventSource = new EventSource(
        api.executionConversationEventsUrl(resolvedProjectId, resolvedNodeId, {
          afterEventSeq: snapshot.record.event_seq,
          expectedStreamId: snapshot.record.active_stream_id,
        }),
      )

      eventSource.onopen = () => {
        if (disposed) {
          return
        }
        useConversationStore.getState().setConnectionStatus(nextConversationId, 'connected')
      }

      eventSource.onmessage = (message) => {
        if (disposed) {
          return
        }
        try {
          const event = JSON.parse(message.data) as ExecutionConversationEvent
          if (event.conversation_id !== nextConversationId) {
            return
          }
          if (isHydrating) {
            bufferedEvents.push(event)
            return
          }
          useConversationStore.getState().applyEvent(nextConversationId, event)
        } catch {
          return
        }
      }

      eventSource.onerror = () => {
        if (disposed) {
          return
        }
        closeStream()
        useConversationStore.getState().setConnectionStatus(nextConversationId, 'reconnecting')
        void reconnect()
      }
    }

    async function reconnect() {
      const refreshed = await hydrateSnapshot('reconnecting')
      if (!refreshed || disposed) {
        return
      }
      openStream(refreshed.snapshot)
    }

    void (async () => {
      const initial = await hydrateSnapshot('connecting')
      if (!initial || disposed) {
        return
      }
      openStream(initial.snapshot)
    })()

    return () => {
      disposed = true
      closeStream()
      const currentConversationId = conversationIdRef.current
      if (currentConversationId) {
        const store = useConversationStore.getState()
        store.setConnectionStatus(currentConversationId, 'disconnected')
        store.setLoading(currentConversationId, false)
        store.setSending(currentConversationId, false)
      }
    }
  }, [enabled, nodeId, projectId])

  async function send(content: string): Promise<ExecutionConversationSendAcceptedResponse | void> {
    const text = content.trim()
    if (!text || !projectId || !nodeId) {
      return
    }
    const currentConversationId = conversationIdRef.current
    if (!currentConversationId) {
      throw new Error('Execution conversation is not ready yet.')
    }
    const store = useConversationStore.getState()
    store.setSending(currentConversationId, true)
    store.setError(currentConversationId, null)
    try {
      const response = await api.sendExecutionConversationMessage(projectId, nodeId, text)
      store.setSending(currentConversationId, false)
      store.setError(currentConversationId, null)
      return response
    } catch (error) {
      store.setSending(currentConversationId, false)
      store.setError(currentConversationId, toErrorMessage(error))
      throw error
    }
  }

  return {
    conversationId,
    conversation,
    bootstrapStatus,
    bootstrapError,
    send,
  }
}
