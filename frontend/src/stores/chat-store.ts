import { create } from 'zustand'
import { api, appendAuthToken, buildChatEventsUrl } from '../api/client'
import type { ChatMessage, ChatSession, MessagePart, ThreadRole } from '../api/types'
import { useDetailStateStore } from './detail-state-store'

const SSE_RECONNECT_RETRY_MS = 1000
const DEFAULT_THREAD_ROLE: ThreadRole = 'ask_planning'

export type ChatStoreState = {
  session: ChatSession | null
  activeProjectId: string | null
  activeNodeId: string | null
  activeThreadRole: ThreadRole
  isLoading: boolean
  isSending: boolean
  error: string | null

  loadSession(projectId: string, nodeId: string, threadRole?: ThreadRole): Promise<void>
  sendMessage(content: string): Promise<void>
  resetSession(): Promise<void>
  disconnect(): void
}

let eventSource: EventSource | null = null
let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null
let sessionGeneration = 0

function closeEventSource() {
  if (eventSource) {
    eventSource.close()
    eventSource = null
  }
}

function clearReconnectTimer() {
  if (reconnectTimer !== null) {
    globalThis.clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
}

function isActiveTarget(
  state: Pick<ChatStoreState, 'activeProjectId' | 'activeNodeId' | 'activeThreadRole'>,
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
) {
  return (
    state.activeProjectId === projectId &&
    state.activeNodeId === nodeId &&
    state.activeThreadRole === threadRole
  )
}

function isCurrentGeneration(generation: number) {
  return generation === sessionGeneration
}

function mergeMessagePair(
  messages: ChatMessage[],
  incoming: [ChatMessage, ChatMessage],
): ChatMessage[] {
  const merged = [...messages]

  for (const candidate of incoming) {
    const existingIndex = merged.findIndex((message) => message.message_id === candidate.message_id)
    if (existingIndex >= 0) {
      merged[existingIndex] = {
        ...merged[existingIndex],
        ...candidate,
      }
      continue
    }
    merged.push(candidate)
  }

  return merged
}

function closeTrailingStreamingPart(parts: MessagePart[]) {
  const lastPart = parts.length > 0 ? parts[parts.length - 1] : null
  if (!lastPart) {
    return
  }
  if (lastPart.type === 'assistant_text') {
    parts[parts.length - 1] = { ...lastPart, is_streaming: false }
  }
  if (lastPart.type === 'plan_item') {
    parts[parts.length - 1] = { ...lastPart, is_streaming: false }
  }
}

function finalizeParts(parts: MessagePart[] | undefined, threadRole: ThreadRole): MessagePart[] {
  const finalizedParts = [...(parts ?? [])].map((part) => {
    if (part.type === 'assistant_text') {
      return { ...part, is_streaming: false }
    }
    if (part.type === 'plan_item') {
      return { ...part, is_streaming: false }
    }
    if (part.type === 'tool_call' && part.status === 'running') {
      return { ...part, status: 'completed' as const }
    }
    return part
  })

  if (threadRole !== 'execution') {
    return finalizedParts.filter((part) => part.type !== 'status_block')
  }

  return finalizedParts
}

function scheduleStreamReopen(
  get: () => ChatStoreState,
  set: (
    partial:
      | Partial<ChatStoreState>
      | ((state: ChatStoreState) => Partial<ChatStoreState>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
  generation: number,
) {
  clearReconnectTimer()
  reconnectTimer = globalThis.setTimeout(() => {
    reconnectTimer = null
    const state = get()
    if (!isCurrentGeneration(generation) || !isActiveTarget(state, projectId, nodeId, threadRole)) {
      return
    }
    openEventStream(get, set, projectId, nodeId, threadRole, generation)
  }, SSE_RECONNECT_RETRY_MS)
}

function scheduleRecoverAndReconnect(
  get: () => ChatStoreState,
  set: (
    partial:
      | Partial<ChatStoreState>
      | ((state: ChatStoreState) => Partial<ChatStoreState>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
  generation: number,
) {
  clearReconnectTimer()
  reconnectTimer = globalThis.setTimeout(() => {
    reconnectTimer = null
    const state = get()
    if (!isCurrentGeneration(generation) || !isActiveTarget(state, projectId, nodeId, threadRole)) {
      return
    }

    void api.getChatSession(projectId, nodeId, threadRole)
      .then((session) => {
        const latestState = get()
        if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
          return
        }
        set({ session, error: null })
        openEventStream(get, set, projectId, nodeId, threadRole, generation)
      })
      .catch((err) => {
        const latestState = get()
        if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
          return
        }
        set({ error: err instanceof Error ? err.message : String(err) })
        scheduleRecoverAndReconnect(get, set, projectId, nodeId, threadRole, generation)
      })
  }, SSE_RECONNECT_RETRY_MS)
}

function openEventStream(
  get: () => ChatStoreState,
  set: (
    partial:
      | Partial<ChatStoreState>
      | ((state: ChatStoreState) => Partial<ChatStoreState>),
  ) => void,
  projectId: string,
  nodeId: string,
  threadRole: ThreadRole,
  generation: number,
) {
  closeEventSource()

  const es = new EventSource(appendAuthToken(buildChatEventsUrl(projectId, nodeId, threadRole)))
  eventSource = es

  es.addEventListener('message', (e) => {
    try {
      if (eventSource !== es || !isCurrentGeneration(generation)) {
        return
      }
      const event = JSON.parse(e.data) as Record<string, unknown>
      const state = get()
      if (state.session && isActiveTarget(state, projectId, nodeId, threadRole)) {
        set({ session: applyChatEvent(state.session, event) })
      }
      if (event.type === 'execution_completed') {
        void useDetailStateStore.getState().refreshExecutionState(projectId, nodeId)
      }
    } catch {
      // Ignore parse errors.
    }
  })

  es.onerror = () => {
    if (eventSource !== es || !isCurrentGeneration(generation)) {
      return
    }

    closeEventSource()
    clearReconnectTimer()

    const state = get()
    if (!isActiveTarget(state, projectId, nodeId, threadRole)) {
      return
    }

    void api.getChatSession(projectId, nodeId, threadRole)
      .then((session) => {
        const latestState = get()
        if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
          return
        }
        set({ session, error: null })
        scheduleStreamReopen(get, set, projectId, nodeId, threadRole, generation)
      })
      .catch((err) => {
        const latestState = get()
        if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
          return
        }
        set({ error: err instanceof Error ? err.message : String(err) })
        scheduleRecoverAndReconnect(get, set, projectId, nodeId, threadRole, generation)
      })
  }
}

function applyChatEvent(session: ChatSession, event: Record<string, unknown>): ChatSession {
  const type = event.type as string

  switch (type) {
    case 'message_created': {
      const userMsg = event.user_message as ChatMessage
      const assistantMsg = event.assistant_message as ChatMessage
      return {
        ...session,
        active_turn_id: event.active_turn_id as string,
        messages: mergeMessagePair(session.messages, [userMsg, assistantMsg]),
      }
    }

    case 'assistant_delta': {
      const messageId = event.message_id as string
      const delta = event.delta as string
      return {
        ...session,
        messages: session.messages.map((message) => {
          if (message.message_id !== messageId) {
            return message
          }
          const parts = [...(message.parts ?? [])]
          closeTrailingStreamingPart(parts)
          const lastPart = parts.length > 0 ? parts[parts.length - 1] : null
          if (lastPart && lastPart.type === 'assistant_text') {
            parts[parts.length - 1] = {
              ...lastPart,
              content: lastPart.content + delta,
              is_streaming: true,
            }
          } else {
            parts.push({ type: 'assistant_text', content: delta, is_streaming: true })
          }
          return {
            ...message,
            content: message.content + delta,
            parts,
            status: 'streaming' as const,
          }
        }),
      }
    }

    case 'assistant_plan_delta': {
      const messageId = event.message_id as string
      const itemId = event.item_id as string
      const delta = event.delta as string
      return {
        ...session,
        messages: session.messages.map((message) => {
          if (message.message_id !== messageId) {
            return message
          }
          const parts = [...(message.parts ?? [])]
          const lastPart = parts.length > 0 ? parts[parts.length - 1] : null
          if (lastPart && lastPart.type === 'plan_item' && lastPart.item_id === itemId) {
            parts[parts.length - 1] = {
              ...lastPart,
              content: lastPart.content + delta,
              is_streaming: true,
              timestamp: new Date().toISOString(),
            }
          } else {
            closeTrailingStreamingPart(parts)
            parts.push({
              type: 'plan_item',
              item_id: itemId,
              content: delta,
              is_streaming: true,
              timestamp: new Date().toISOString(),
            })
          }
          return {
            ...message,
            parts,
            status: 'streaming' as const,
          }
        }),
      }
    }

    case 'assistant_tool_call': {
      const messageId = event.message_id as string
      const toolName = event.tool_name as string
      const args = (event.arguments ?? {}) as Record<string, unknown>
      const callId = (event.call_id as string | null | undefined) ?? null
      return {
        ...session,
        messages: session.messages.map((message) => {
          if (message.message_id !== messageId) {
            return message
          }
          const parts: MessagePart[] = [...(message.parts ?? [])]
          closeTrailingStreamingPart(parts)
          parts.push({
            type: 'tool_call',
            tool_name: toolName,
            arguments: args,
            call_id: callId,
            status: 'running',
            output: null,
            exit_code: null,
          })
          return { ...message, parts }
        }),
      }
    }

    case 'assistant_tool_result': {
      const messageId = event.message_id as string
      const callId = (event.call_id as string | null | undefined) ?? null
      const status = event.status as 'completed' | 'error'
      const output = (event.output as string | null | undefined) ?? null
      const exitCode = typeof event.exit_code === 'number' ? event.exit_code : null
      return {
        ...session,
        messages: session.messages.map((message) => {
          if (message.message_id !== messageId) {
            return message
          }
          const parts: MessagePart[] = [...(message.parts ?? [])]
          const targetIndex = parts.findLastIndex(
            (part) => part.type === 'tool_call' && (callId ? part.call_id === callId : part.status === 'running'),
          )
          if (targetIndex === -1) {
            return message
          }
          const target = parts[targetIndex]
          if (target.type !== 'tool_call') {
            return message
          }
          parts[targetIndex] = {
            ...target,
            status,
            output,
            exit_code: exitCode,
          }
          return { ...message, parts }
        }),
      }
    }

    case 'assistant_status': {
      const messageId = event.message_id as string
      const statusType = event.status_type as string
      const label = event.label as string
      return {
        ...session,
        messages: session.messages.map((message) => {
          if (message.message_id !== messageId) {
            return message
          }
          const parts: MessagePart[] = [...(message.parts ?? [])]
          closeTrailingStreamingPart(parts)
          const statusPart: MessagePart = {
            type: 'status_block',
            status_type: statusType,
            label,
            timestamp: new Date().toISOString(),
          }
          const lastPart = parts.length > 0 ? parts[parts.length - 1] : null
          if (lastPart && lastPart.type === 'status_block') {
            parts[parts.length - 1] = statusPart
          } else {
            parts.push(statusPart)
          }
          return { ...message, parts }
        }),
      }
    }

    case 'assistant_completed': {
      const messageId = event.message_id as string
      const content = event.content as string
      const threadId = event.thread_id as string
      return {
        ...session,
        active_turn_id: null,
        thread_id: threadId,
        messages: session.messages.map((message) => {
          if (message.message_id !== messageId) {
            return message
          }
          const parts = finalizeParts(message.parts, session.thread_role)
          return { ...message, content, parts, status: 'completed' as const }
        }),
      }
    }

    case 'assistant_error': {
      const messageId = event.message_id as string
      const error = event.error as string
      return {
        ...session,
        active_turn_id: null,
        messages: session.messages.map((message) => {
          if (message.message_id !== messageId) {
            return message
          }
          return { ...message, status: 'error' as const, error }
        }),
      }
    }

    default:
      return session
  }
}

export const useChatStore = create<ChatStoreState>((set, get) => ({
  session: null,
  activeProjectId: null,
  activeNodeId: null,
  activeThreadRole: DEFAULT_THREAD_ROLE,
  isLoading: false,
  isSending: false,
  error: null,

  async loadSession(projectId: string, nodeId: string, threadRole: ThreadRole = DEFAULT_THREAD_ROLE) {
    const current = get()
    if (
      current.activeProjectId === projectId &&
      current.activeNodeId === nodeId &&
      current.activeThreadRole === threadRole &&
      current.session &&
      (eventSource !== null || reconnectTimer !== null)
    ) {
      return
    }

    clearReconnectTimer()
    closeEventSource()
    const generation = ++sessionGeneration
    set({
      isLoading: true,
      isSending: false,
      error: null,
      activeProjectId: projectId,
      activeNodeId: nodeId,
      activeThreadRole: threadRole,
      session: null,
    })

    try {
      const session = await api.getChatSession(projectId, nodeId, threadRole)
      const latestState = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
        return
      }
      set({ session, isLoading: false, error: null })
      openEventStream(get, set, projectId, nodeId, threadRole, generation)
    } catch (err) {
      const latestState = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(latestState, projectId, nodeId, threadRole)) {
        return
      }
      set({
        error: err instanceof Error ? err.message : String(err),
        isLoading: false,
      })
    }
  },

  async sendMessage(content: string) {
    const { activeProjectId, activeNodeId, activeThreadRole, session } = get()
    if (!activeProjectId || !activeNodeId || !session) {
      return
    }

    const generation = sessionGeneration
    set({ isSending: true, error: null })
    try {
      const result = await api.sendChatMessage(activeProjectId, activeNodeId, content, activeThreadRole)
      set((state) => {
        if (
          !isCurrentGeneration(generation) ||
          !state.session ||
          !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)
        ) {
          return {}
        }
        return {
          isSending: false,
          session: {
            ...state.session,
            active_turn_id: result.active_turn_id,
            messages: mergeMessagePair(
              state.session.messages,
              [result.user_message, result.assistant_message],
            ),
          },
        }
      })
      if (activeThreadRole === 'audit') {
        void useDetailStateStore.getState().refreshExecutionState(activeProjectId, activeNodeId)
      }
    } catch (err) {
      const state = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)) {
        return
      }
      set({
        error: err instanceof Error ? err.message : String(err),
        isSending: false,
      })
    }
  },

  async resetSession() {
    const { activeProjectId, activeNodeId, activeThreadRole } = get()
    if (!activeProjectId || !activeNodeId) {
      return
    }

    const generation = sessionGeneration
    set({ error: null })
    try {
      const session = await api.resetChatSession(activeProjectId, activeNodeId, activeThreadRole)
      set((state) => {
        if (!isCurrentGeneration(generation) || !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)) {
          return {}
        }
        return { session }
      })
    } catch (err) {
      const state = get()
      if (!isCurrentGeneration(generation) || !isActiveTarget(state, activeProjectId, activeNodeId, activeThreadRole)) {
        return
      }
      set({ error: err instanceof Error ? err.message : String(err) })
    }
  },

  disconnect() {
    sessionGeneration += 1
    clearReconnectTimer()
    closeEventSource()
    set({
      session: null,
      activeProjectId: null,
      activeNodeId: null,
      activeThreadRole: DEFAULT_THREAD_ROLE,
      error: null,
      isLoading: false,
      isSending: false,
    })
  },
}))

export { applyChatEvent }
