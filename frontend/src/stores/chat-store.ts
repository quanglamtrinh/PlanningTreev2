import { create } from 'zustand'

import { api, ApiError } from '../api/client'
import type { ChatEvent, ChatMessage, ChatSession, RuntimeInputRequest } from '../api/types'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

function markPerformance(name: string) {
  if (typeof window === 'undefined' || typeof window.performance?.mark !== 'function') {
    return
  }
  window.performance.mark(name)
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

function upsertMessage(messages: ChatMessage[], nextMessage: ChatMessage): ChatMessage[] {
  const index = messages.findIndex((item) => item.message_id === nextMessage.message_id)
  if (index < 0) {
    return [...messages, nextMessage]
  }
  const next = [...messages]
  next[index] = { ...next[index], ...nextMessage }
  return next
}

function upsertRuntimeRequest(
  requests: RuntimeInputRequest[] | undefined,
  nextRequest: RuntimeInputRequest,
): RuntimeInputRequest[] {
  const list = requests ?? []
  const index = list.findIndex((item) => item.request_id === nextRequest.request_id)
  if (index < 0) {
    return [...list, nextRequest]
  }
  const next = [...list]
  next[index] = { ...next[index], ...nextRequest }
  return next
}

type ChatStoreState = {
  session: ChatSession | null
  composerDraft: string
  connectionStatus: ConnectionStatus
  isLoadingSession: boolean
  isSendingMessage: boolean
  error: string | null
  loadSession: (projectId: string, nodeId: string) => Promise<void>
  sendMessage: (projectId: string, nodeId: string, content: string) => Promise<void>
  resetSession: (projectId: string, nodeId: string) => Promise<void>
  setComposerDraft: (draft: string) => void
  setConnectionStatus: (status: ConnectionStatus) => void
  applyChatEvent: (event: ChatEvent) => void
  clearSession: (preserveComposerDraft?: boolean) => void
}

export const useChatStore = create<ChatStoreState>((set) => ({
  session: null,
  composerDraft: '',
  connectionStatus: 'disconnected',
  isLoadingSession: false,
  isSendingMessage: false,
  error: null,
  async loadSession(projectId: string, nodeId: string) {
    set({ isLoadingSession: true, error: null })
    try {
      const response = await api.getChatSession(projectId, nodeId)
      set({ session: response.session, isLoadingSession: false, error: null })
    } catch (error) {
      set({ error: toErrorMessage(error), isLoadingSession: false })
      throw error
    }
  },
  async sendMessage(projectId: string, nodeId: string, content: string) {
    const text = content.trim()
    if (!text) {
      return
    }
    set({ isSendingMessage: true, error: null })
    try {
      const session = useChatStore.getState().session
      if (session?.mode === 'plan') {
        markPerformance('agent_click')
        await api.sendPlanMessage(projectId, nodeId, text)
      } else {
        await api.sendChatMessage(projectId, nodeId, text)
      }
      set({ composerDraft: '', isSendingMessage: false, error: null })
    } catch (error) {
      set({ error: toErrorMessage(error), isSendingMessage: false })
      throw error
    }
  },
  async resetSession(projectId: string, nodeId: string) {
    set({ error: null })
    try {
      const response = await api.resetChatSession(projectId, nodeId)
      set({ session: response.session, composerDraft: '', error: null })
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  setComposerDraft(composerDraft) {
    set({ composerDraft })
  },
  setConnectionStatus(connectionStatus) {
    set({ connectionStatus })
  },
  applyChatEvent(event) {
    set((state) => {
      const current = state.session
      if (current && event.event_seq <= current.event_seq) {
        return {}
      }

      if (!current) {
        if (event.type === 'session_reset') {
          return { session: event.session }
        }
        return {}
      }

      switch (event.type) {
        case 'message_created':
          return {
            session: {
              ...current,
              event_seq: event.event_seq,
              active_turn_id: event.active_turn_id,
              messages: upsertMessage(
                upsertMessage(current.messages, event.user_message),
                event.assistant_message,
              ),
            },
          }
        case 'assistant_delta':
          if (current.mode === 'plan') {
            markPerformance('agent_first_content_visible')
          }
          return {
            session: {
              ...current,
              event_seq: event.event_seq,
              messages: current.messages.map((message) =>
                message.message_id === event.message_id
                  ? {
                      ...message,
                      content: event.content,
                      status: 'streaming',
                      updated_at: event.updated_at,
                    }
                  : message,
              ),
            },
          }
        case 'assistant_completed':
          return {
            session: {
              ...current,
              event_seq: event.event_seq,
              active_turn_id: null,
              messages: current.messages.map((message) =>
                message.message_id === event.message_id
                  ? {
                      ...message,
                      content: event.content,
                      status: 'completed',
                      updated_at: event.updated_at,
                      error: null,
                    }
                  : message,
              ),
            },
          }
        case 'assistant_error':
          return {
            session: {
              ...current,
              event_seq: event.event_seq,
              active_turn_id: null,
              messages: current.messages.map((message) =>
                message.message_id === event.message_id
                  ? {
                      ...message,
                      content: event.content,
                      status: 'error',
                      updated_at: event.updated_at,
                      error: event.error,
                    }
                  : message,
              ),
            },
          }
        case 'session_reset':
          return { session: event.session }
        case 'plan_input_requested':
          return {
            session: {
              ...current,
              event_seq: event.event_seq,
              pending_input_request: event.request,
              runtime_request_registry: upsertRuntimeRequest(
                current.runtime_request_registry,
                event.request,
              ),
              messages: upsertMessage(current.messages, event.assistant_message),
            },
          }
        case 'plan_input_resolved': {
          const nextRegistry = (current.runtime_request_registry ?? []).map((request) =>
            request.request_id === event.request_id
              ? {
                  ...request,
                  status: event.status,
                  resolved_at: event.resolved_at,
                }
              : request,
          )
          return {
            session: {
              ...current,
              event_seq: event.event_seq,
              pending_input_request:
                current.pending_input_request?.request_id === event.request_id
                  ? null
                  : current.pending_input_request ?? null,
              runtime_request_registry: nextRegistry,
              messages: event.user_message
                ? upsertMessage(current.messages, event.user_message)
                : current.messages,
            },
          }
        }
        case 'plan_runtime_status_changed':
          return {
            session: {
              ...current,
              event_seq: event.event_seq,
              runtime_thread_status: event.thread_status,
            },
          }
      }
    })
  },
  clearSession(preserveComposerDraft = false) {
    set({
      session: null,
      composerDraft: preserveComposerDraft ? useChatStore.getState().composerDraft : '',
      connectionStatus: 'disconnected',
      isLoadingSession: false,
      isSendingMessage: false,
      error: null,
    })
  },
}))
