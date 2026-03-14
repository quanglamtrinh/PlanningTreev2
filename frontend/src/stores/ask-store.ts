import { create } from 'zustand'

import { api, ApiError } from '../api/client'
import type { AskEvent, AskSession, ChatMessage, DeltaContextPacket } from '../api/types'

export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'

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

function upsertPacket(packets: DeltaContextPacket[], nextPacket: DeltaContextPacket): DeltaContextPacket[] {
  const index = packets.findIndex((packet) => packet.packet_id === nextPacket.packet_id)
  if (index < 0) {
    return [...packets, nextPacket]
  }
  const next = [...packets]
  next[index] = { ...next[index], ...nextPacket }
  return next
}

type AskStoreState = {
  session: AskSession | null
  composerDraft: string
  connectionStatus: ConnectionStatus
  isLoadingSession: boolean
  isSendingMessage: boolean
  error: string | null
  loadSession: (projectId: string, nodeId: string) => Promise<void>
  sendMessage: (projectId: string, nodeId: string, content: string) => Promise<void>
  resetSession: (projectId: string, nodeId: string) => Promise<void>
  approvePacket: (projectId: string, nodeId: string, packetId: string) => Promise<void>
  rejectPacket: (projectId: string, nodeId: string, packetId: string) => Promise<void>
  mergePacket: (projectId: string, nodeId: string, packetId: string) => Promise<void>
  setComposerDraft: (draft: string) => void
  setConnectionStatus: (status: ConnectionStatus) => void
  applyAskEvent: (event: AskEvent) => void
  clearSession: (preserveComposerDraft?: boolean) => void
}

export const useAskStore = create<AskStoreState>((set) => ({
  session: null,
  composerDraft: '',
  connectionStatus: 'disconnected',
  isLoadingSession: false,
  isSendingMessage: false,
  error: null,
  async loadSession(projectId: string, nodeId: string) {
    set({ isLoadingSession: true, error: null })
    try {
      const response = await api.getAskSession(projectId, nodeId)
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
      await api.sendAskMessage(projectId, nodeId, text)
      set({ composerDraft: '', isSendingMessage: false, error: null })
    } catch (error) {
      set({ error: toErrorMessage(error), isSendingMessage: false })
      throw error
    }
  },
  async resetSession(projectId: string, nodeId: string) {
    set({ error: null })
    try {
      const response = await api.resetAskSession(projectId, nodeId)
      set({ session: response.session, composerDraft: '', error: null })
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  async approvePacket(projectId: string, nodeId: string, packetId: string) {
    set({ error: null })
    try {
      const response = await api.approveAskPacket(projectId, nodeId, packetId)
      set((state) => ({
        session: state.session
          ? {
              ...state.session,
              delta_context_packets: upsertPacket(state.session.delta_context_packets, response.packet),
            }
          : null,
        error: null,
      }))
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  async rejectPacket(projectId: string, nodeId: string, packetId: string) {
    set({ error: null })
    try {
      const response = await api.rejectAskPacket(projectId, nodeId, packetId)
      set((state) => ({
        session: state.session
          ? {
              ...state.session,
              delta_context_packets: upsertPacket(state.session.delta_context_packets, response.packet),
            }
          : null,
        error: null,
      }))
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  async mergePacket(projectId: string, nodeId: string, packetId: string) {
    set({ error: null })
    try {
      const response = await api.mergeAskPacket(projectId, nodeId, packetId)
      set((state) => ({
        session: state.session
          ? {
              ...state.session,
              delta_context_packets: upsertPacket(state.session.delta_context_packets, response.packet),
            }
          : null,
        error: null,
      }))
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
  applyAskEvent(event) {
    set((state) => {
      const current = state.session
      if (current && event.event_seq <= current.event_seq) {
        return {}
      }

      if (!current) {
        if (event.type === 'ask_session_reset') {
          return { session: event.session }
        }
        return {}
      }

      switch (event.type) {
        case 'ask_message_created':
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
        case 'ask_assistant_delta':
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
        case 'ask_assistant_completed':
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
        case 'ask_assistant_error':
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
        case 'ask_session_reset':
          return { session: event.session }
        case 'ask_delta_context_suggested':
          return {
            session: {
              ...current,
              event_seq: event.event_seq,
              delta_context_packets: upsertPacket(current.delta_context_packets, event.packet),
            },
          }
        case 'ask_packet_status_changed':
          return {
            session: {
              ...current,
              event_seq: event.event_seq,
              delta_context_packets: upsertPacket(current.delta_context_packets, event.packet),
            },
          }
      }
    })
  },
  clearSession(preserveComposerDraft = false) {
    set({
      session: null,
      composerDraft: preserveComposerDraft ? useAskStore.getState().composerDraft : '',
      connectionStatus: 'disconnected',
      isLoadingSession: false,
      isSendingMessage: false,
      error: null,
    })
  },
}))
