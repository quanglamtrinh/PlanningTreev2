import type { AskSession, ChatMessage, ChatSession } from '../../../api/types'
import type {
  ConversationMessage,
  ConversationMessagePart,
  ConversationRuntimeMode,
  ConversationScope,
  ConversationSnapshot,
  ConversationThreadType,
} from '../types'

function toMessageStatus(status: ChatMessage['status']): ConversationMessage['status'] {
  return status
}

function defaultRuntimeMode(threadType: ConversationThreadType): ConversationRuntimeMode {
  if (threadType === 'execution') {
    return 'execute'
  }
  return threadType
}

function toMessagePart(message: ChatMessage): ConversationMessagePart {
  return {
    part_id: `${message.message_id}:text`,
    part_type: message.role === 'assistant' ? 'assistant_text' : 'user_text',
    status: toMessageStatus(message.status),
    order: 0,
    item_key: null,
    created_at: message.created_at,
    updated_at: message.updated_at,
    payload: {
      content: message.content,
    },
  }
}

function toConversationMessage(
  message: ChatMessage,
  options: {
    conversationId: string
    runtimeMode: ConversationRuntimeMode
  },
): ConversationMessage {
  return {
    message_id: message.message_id,
    conversation_id: options.conversationId,
    turn_id: message.message_id,
    role: message.role,
    runtime_mode: options.runtimeMode,
    status: toMessageStatus(message.status),
    created_at: message.created_at,
    updated_at: message.updated_at,
    lineage: {},
    usage: null,
    error: message.error,
    parts: [toMessagePart(message)],
  }
}

function buildSnapshot(
  scope: ConversationScope,
  options: {
    conversationId: string
    runtimeMode: ConversationRuntimeMode
    appServerThreadId: string | null
    activeStreamId: string | null
    eventSeq: number
    status: ConversationSnapshot['record']['status']
    messages: ChatMessage[]
  },
): ConversationSnapshot {
  const createdAt = options.messages[0]?.created_at ?? new Date(0).toISOString()
  const updatedAt = options.messages[options.messages.length - 1]?.updated_at ?? createdAt
  return {
    record: {
      conversation_id: options.conversationId,
      project_id: scope.project_id,
      node_id: scope.node_id,
      thread_type: scope.thread_type,
      app_server_thread_id: options.appServerThreadId,
      current_runtime_mode: options.runtimeMode,
      status: options.status,
      active_stream_id: options.activeStreamId,
      event_seq: options.eventSeq,
      created_at: createdAt,
      updated_at: updatedAt,
    },
    messages: options.messages.map((message) =>
      toConversationMessage(message, {
        conversationId: options.conversationId,
        runtimeMode: options.runtimeMode,
      }),
    ),
  }
}

export function adaptLegacyChatSessionToConversation(
  scope: ConversationScope,
  session: ChatSession,
  conversationId: string,
): ConversationSnapshot {
  const runtimeMode =
    session.mode === 'plan' ? 'plan' : session.mode === 'execute' ? 'execute' : defaultRuntimeMode(scope.thread_type)

  return buildSnapshot(scope, {
    conversationId,
    runtimeMode,
    appServerThreadId: null,
    activeStreamId: null,
    eventSeq: session.event_seq,
    status: session.status === 'active' ? 'active' : 'idle',
    messages: session.messages,
  })
}

export function adaptLegacyAskSessionToConversation(
  scope: ConversationScope,
  session: AskSession,
  conversationId: string,
): ConversationSnapshot {
  return buildSnapshot(scope, {
    conversationId,
    runtimeMode: 'ask',
    appServerThreadId: null,
    activeStreamId: null,
    eventSeq: session.event_seq,
    status: session.status === 'active' ? 'active' : 'idle',
    messages: session.messages,
  })
}
