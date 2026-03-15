import { create } from 'zustand'

import {
  createConversationScopeKey,
  type ConversationEventEnvelope,
  type ConversationMessage,
  type ConversationMessagePart,
  type ConversationRecord,
  type ConversationScope,
  type ConversationSnapshot,
} from '../features/conversation/types'
import { applyConversationEvent } from '../features/conversation/model/applyConversationEvent'

export type ConversationConnectionStatus =
  | 'idle'
  | 'loading_snapshot'
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'error'

export type ConversationErrorKind = 'send' | 'reconnect_exhausted' | null

export interface ConversationViewState {
  snapshot: ConversationSnapshot
  composerDraft: string
  connectionStatus: ConversationConnectionStatus
  isLoading: boolean
  isSending: boolean
  error: string | null
  errorKind: ConversationErrorKind
}

type ConversationStoreState = {
  conversationsById: Record<string, ConversationViewState>
  scopeIndex: Record<string, string>
  ensureConversation: (snapshot: ConversationSnapshot) => string
  hydrateConversation: (snapshot: ConversationSnapshot) => void
  getConversationIdByScope: (scope: ConversationScope) => string | null
  setComposerDraft: (conversationId: string, draft: string) => void
  setLoading: (conversationId: string, isLoading: boolean) => void
  setSending: (conversationId: string, isSending: boolean) => void
  setError: (
    conversationId: string,
    error: string | null,
    errorKind?: ConversationErrorKind,
  ) => void
  setConnectionStatus: (
    conversationId: string,
    status: ConversationConnectionStatus,
  ) => void
  patchRecord: (
    conversationId: string,
    patch: Partial<ConversationRecord>,
  ) => void
  upsertMessage: (conversationId: string, message: ConversationMessage) => void
  upsertPart: (
    conversationId: string,
    messageId: string,
    part: ConversationMessagePart,
  ) => void
  setActiveStream: (conversationId: string, streamId: string | null) => void
  advanceEventSeq: (conversationId: string, eventSeq: number) => void
  applyEvent: (conversationId: string, event: ConversationEventEnvelope) => void
  clearConversation: (conversationId: string) => void
}

function mergeMessages(
  messages: ConversationMessage[],
  nextMessage: ConversationMessage,
): ConversationMessage[] {
  const index = messages.findIndex((message) => message.message_id === nextMessage.message_id)
  if (index < 0) {
    return [...messages, nextMessage]
  }
  const next = [...messages]
  next[index] = nextMessage
  return next
}

function mergeParts(
  parts: ConversationMessagePart[],
  nextPart: ConversationMessagePart,
): ConversationMessagePart[] {
  const index = parts.findIndex((part) => part.part_id === nextPart.part_id)
  if (index < 0) {
    return [...parts, nextPart].sort(
      (left, right) => left.order - right.order || left.part_id.localeCompare(right.part_id),
    )
  }
  const next = [...parts]
  next[index] = nextPart
  return next.sort(
    (left, right) => left.order - right.order || left.part_id.localeCompare(right.part_id),
  )
}

function createConversationViewState(snapshot: ConversationSnapshot): ConversationViewState {
  return {
    snapshot,
    composerDraft: '',
    connectionStatus: 'idle',
    isLoading: false,
    isSending: false,
    error: null,
    errorKind: null,
  }
}

export const useConversationStore = create<ConversationStoreState>((set, get) => ({
  conversationsById: {},
  scopeIndex: {},
  ensureConversation(snapshot) {
    const conversationId = snapshot.record.conversation_id
    const scopeKey = createConversationScopeKey(snapshot.record)
    set((state) => {
      if (state.conversationsById[conversationId]) {
        return {
          scopeIndex: {
            ...state.scopeIndex,
            [scopeKey]: conversationId,
          },
        }
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: createConversationViewState(snapshot),
        },
        scopeIndex: {
          ...state.scopeIndex,
          [scopeKey]: conversationId,
        },
      }
    })
    return conversationId
  },
  hydrateConversation(snapshot) {
    const conversationId = snapshot.record.conversation_id
    const scopeKey = createConversationScopeKey(snapshot.record)
    set((state) => {
      const current = state.conversationsById[conversationId]
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...(current ?? createConversationViewState(snapshot)),
            snapshot,
          },
        },
        scopeIndex: {
          ...state.scopeIndex,
          [scopeKey]: conversationId,
        },
      }
    })
  },
  getConversationIdByScope(scope) {
    return get().scopeIndex[createConversationScopeKey(scope)] ?? null
  },
  setComposerDraft(conversationId, draft) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            composerDraft: draft,
          },
        },
      }
    })
  },
  setLoading(conversationId, isLoading) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            isLoading,
          },
        },
      }
    })
  },
  setSending(conversationId, isSending) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            isSending,
          },
        },
      }
    })
  },
  setError(conversationId, error, errorKind = null) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            error,
            errorKind: error ? errorKind : null,
          },
        },
      }
    })
  },
  setConnectionStatus(conversationId, status) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            connectionStatus: status,
          },
        },
      }
    })
  },
  patchRecord(conversationId, patch) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            snapshot: {
              ...current.snapshot,
              record: {
                ...current.snapshot.record,
                ...patch,
              },
            },
          },
        },
      }
    })
  },
  upsertMessage(conversationId, message) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            snapshot: {
              ...current.snapshot,
              record: {
                ...current.snapshot.record,
                updated_at: message.updated_at,
              },
              messages: mergeMessages(current.snapshot.messages, message),
            },
          },
        },
      }
    })
  },
  upsertPart(conversationId, messageId, part) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }

      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            snapshot: {
              ...current.snapshot,
              record: {
                ...current.snapshot.record,
                updated_at: part.updated_at,
              },
              messages: current.snapshot.messages.map((message) =>
                message.message_id === messageId
                  ? {
                      ...message,
                      updated_at: part.updated_at,
                      parts: mergeParts(message.parts, part),
                    }
                  : message,
              ),
            },
          },
        },
      }
    })
  },
  setActiveStream(conversationId, streamId) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            snapshot: {
              ...current.snapshot,
              record: {
                ...current.snapshot.record,
                active_stream_id: streamId,
              },
            },
          },
        },
      }
    })
  },
  advanceEventSeq(conversationId, eventSeq) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current || eventSeq <= current.snapshot.record.event_seq) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            snapshot: {
              ...current.snapshot,
              record: {
                ...current.snapshot.record,
                event_seq: eventSeq,
              },
            },
          },
        },
      }
    })
  },
  applyEvent(conversationId, event) {
    set((state) => {
      const current = state.conversationsById[conversationId]
      if (!current) {
        return {}
      }
      return {
        conversationsById: {
          ...state.conversationsById,
          [conversationId]: {
            ...current,
            snapshot: applyConversationEvent(current.snapshot, event),
          },
        },
      }
    })
  },
  clearConversation(conversationId) {
    set((state) => {
      const nextConversations = { ...state.conversationsById }
      const removed = nextConversations[conversationId]
      if (!removed) {
        return {}
      }
      delete nextConversations[conversationId]

      const nextScopeIndex = { ...state.scopeIndex }
      const scopeKey = createConversationScopeKey(removed.snapshot.record)
      delete nextScopeIndex[scopeKey]

      return {
        conversationsById: nextConversations,
        scopeIndex: nextScopeIndex,
      }
    })
  },
}))
