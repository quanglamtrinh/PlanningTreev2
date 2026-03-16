import type { ConversationMessage, ConversationMessagePart, ConversationSnapshot } from '../types'

function isBusyStatus(status: ConversationMessage['status'] | ConversationMessagePart['status']): boolean {
  return status === 'pending' || status === 'streaming'
}

function findLatestAssistantMessage(snapshot: ConversationSnapshot): ConversationMessage | null {
  for (let index = snapshot.messages.length - 1; index >= 0; index -= 1) {
    const message = snapshot.messages[index]
    if (message.role === 'assistant') {
      return message
    }
  }
  return null
}

function findLatestAssistantTextPart(message: ConversationMessage): ConversationMessagePart | null {
  for (let index = message.parts.length - 1; index >= 0; index -= 1) {
    const part = message.parts[index]
    if (part.part_type === 'assistant_text') {
      return part
    }
  }
  return null
}

export function deriveConversationBusy(snapshot: ConversationSnapshot | null | undefined): boolean {
  if (!snapshot) {
    return false
  }

  if (snapshot.record.active_stream_id !== null) {
    return true
  }

  if (snapshot.record.status === 'active') {
    return true
  }

  const latestAssistantMessage = findLatestAssistantMessage(snapshot)
  if (!latestAssistantMessage) {
    return false
  }

  if (isBusyStatus(latestAssistantMessage.status)) {
    return true
  }

  const latestAssistantTextPart = findLatestAssistantTextPart(latestAssistantMessage)
  return latestAssistantTextPart ? isBusyStatus(latestAssistantTextPart.status) : false
}
