import type { ConversationMessage, ConversationMessagePart, ConversationSnapshot } from '../types'

export type ConversationRenderRoleTone = 'user' | 'assistant' | 'neutral'

export interface ConversationRenderMessage {
  messageId: string
  roleTone: ConversationRenderRoleTone
  text: string
  isStreaming: boolean
  hasError: boolean
  errorText?: string
  showTyping: boolean
  unsupportedPartTypes: string[]
}

export interface ConversationRenderModel {
  messages: ConversationRenderMessage[]
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function readPartText(part: ConversationMessagePart): string {
  const text = asString(part.payload.text)
  if (text !== null) {
    return text
  }
  return asString(part.payload.content) ?? ''
}

function toRoleTone(role: string): ConversationRenderRoleTone {
  if (role === 'user') {
    return 'user'
  }
  if (role === 'assistant') {
    return 'assistant'
  }
  return 'neutral'
}

function expectedTextPartType(role: string): ConversationMessagePart['part_type'] | null {
  if (role === 'user') {
    return 'user_text'
  }
  if (role === 'assistant') {
    return 'assistant_text'
  }
  return null
}

function appendUnique(values: string[], nextValue: string) {
  if (!values.includes(nextValue)) {
    values.push(nextValue)
  }
}

function isStreamingStatus(status: ConversationMessage['status'] | ConversationMessagePart['status']): boolean {
  return status === 'pending' || status === 'streaming'
}

function buildConversationRenderMessage(message: ConversationMessage): ConversationRenderMessage {
  const roleTone = toRoleTone(message.role)
  const supportedPartType = expectedTextPartType(message.role)
  const unsupportedPartTypes: string[] = []
  let text = ''
  let partStreaming = false
  let partError = false

  for (const part of message.parts) {
    if (supportedPartType !== null && part.part_type === supportedPartType) {
      text += readPartText(part)
      partStreaming ||= isStreamingStatus(part.status)
      partError ||= part.status === 'error'
      continue
    }
    appendUnique(unsupportedPartTypes, part.part_type)
  }

  const isStreaming = isStreamingStatus(message.status) || partStreaming
  const hasError = message.status === 'error' || partError || Boolean(message.error)

  return {
    messageId: message.message_id,
    roleTone,
    text,
    isStreaming,
    hasError,
    errorText: message.error ?? undefined,
    showTyping: roleTone === 'assistant' && isStreaming && text.length === 0,
    unsupportedPartTypes,
  }
}

export function buildConversationRenderModel(
  snapshot: ConversationSnapshot | null | undefined,
): ConversationRenderModel | null {
  if (!snapshot) {
    return null
  }

  return {
    messages: snapshot.messages.map(buildConversationRenderMessage),
  }
}
