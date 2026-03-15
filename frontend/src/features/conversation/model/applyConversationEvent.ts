import type {
  ConversationEventEnvelope,
  ConversationMessage,
  ConversationMessagePart,
  ConversationMessageStatus,
  ConversationRecord,
  ConversationSnapshot,
  ConversationStatus,
} from '../types'

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function readEventStreamId(event: ConversationEventEnvelope): string | null {
  return asString((event as unknown as Record<string, unknown>).stream_id)
}

function readPartText(part: ConversationMessagePart): string {
  const text = asString(part.payload.text)
  if (text !== null) {
    return text
  }
  return asString(part.payload.content) ?? ''
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

function updateRecord(
  record: ConversationRecord,
  event: ConversationEventEnvelope,
  patch: Partial<ConversationRecord>,
): ConversationRecord {
  return {
    ...record,
    ...patch,
    event_seq: event.event_seq,
    updated_at: event.created_at,
  }
}

function updateMessageStatus(
  message: ConversationMessage,
  status: ConversationMessageStatus,
  updatedAt: string,
  error: string | null,
): ConversationMessage {
  return {
    ...message,
    status,
    updated_at: updatedAt,
    error,
    parts: message.parts.map((part) => ({
      ...part,
      status,
      updated_at: updatedAt,
    })),
  }
}

function updateAssistantTextPart(
  message: ConversationMessage,
  partId: string,
  nextText: string,
  status: ConversationMessageStatus,
  updatedAt: string,
): ConversationMessage {
  return {
    ...message,
    status,
    updated_at: updatedAt,
    parts: mergeParts(
      message.parts,
      message.parts.reduce<ConversationMessagePart | null>((match, part) => {
        if (match || part.part_id !== partId) {
          return match
        }
        return {
          ...part,
          status,
          updated_at: updatedAt,
          payload: {
            ...part.payload,
            text: nextText,
            content: nextText,
          },
        }
      }, null) ?? {
        part_id: partId,
        part_type: 'assistant_text',
        status,
        order: message.parts.length,
        item_key: null,
        created_at: updatedAt,
        updated_at: updatedAt,
        payload: {
          text: nextText,
          content: nextText,
        },
      },
    ),
  }
}

function toConversationStatus(value: unknown): ConversationStatus | null {
  return value === 'idle' ||
    value === 'active' ||
    value === 'completed' ||
    value === 'interrupted' ||
    value === 'cancelled' ||
    value === 'error'
    ? value
    : null
}

function toMessageStatus(value: unknown): ConversationMessageStatus | null {
  return value === 'pending' ||
    value === 'streaming' ||
    value === 'completed' ||
    value === 'error' ||
    value === 'cancelled' ||
    value === 'interrupted' ||
    value === 'superseded'
    ? value
    : null
}

export function shouldAcceptConversationEvent(
  snapshot: ConversationSnapshot,
  event: ConversationEventEnvelope,
): boolean {
  if (
    event.conversation_id !== snapshot.record.conversation_id ||
    event.event_seq <= snapshot.record.event_seq
  ) {
    return false
  }

  const streamId = readEventStreamId(event)
  if (!streamId) {
    return false
  }

  const activeStreamId = snapshot.record.active_stream_id
  switch (event.event_type) {
    case 'message_created':
      return activeStreamId === null || streamId === activeStreamId
    case 'assistant_text_delta':
    case 'assistant_text_final':
    case 'completion_status':
      return activeStreamId !== null && streamId === activeStreamId
    default:
      return false
  }
}

export function applyConversationEvent(
  snapshot: ConversationSnapshot,
  event: ConversationEventEnvelope,
): ConversationSnapshot {
  if (!shouldAcceptConversationEvent(snapshot, event)) {
    return snapshot
  }

  const payload = asRecord(event.payload) ?? {}
  const streamId = readEventStreamId(event)
  if (!streamId) {
    return snapshot
  }

  switch (event.event_type) {
    case 'message_created': {
      const message = payload.message as ConversationMessage | undefined
      if (!message) {
        return {
          ...snapshot,
          record: updateRecord(snapshot.record, event, {
            active_stream_id: streamId,
            status: 'active',
          }),
        }
      }
      return {
        ...snapshot,
        record: updateRecord(snapshot.record, event, {
          active_stream_id: streamId,
          current_runtime_mode: message.runtime_mode,
          status: 'active',
        }),
        messages: mergeMessages(snapshot.messages, message),
      }
    }
    case 'assistant_text_delta':
    case 'assistant_text_final': {
      const messageStatus = toMessageStatus(payload.status) ?? 'streaming'
      const partId = asString(event.item_id) ?? asString(payload.part_id) ?? null
      const delta = asString(payload.delta) ?? ''
      const text = asString(payload.text)
      const updatedMessages = snapshot.messages.map((message) => {
        if (message.message_id !== event.message_id || !partId) {
          return message
        }
        const currentPart =
          message.parts.find((part) => part.part_id === partId) ?? null
        const nextText =
          text ?? `${currentPart ? readPartText(currentPart) : ''}${delta}`
        return updateAssistantTextPart(message, partId, nextText, messageStatus, event.created_at)
      })
      return {
        ...snapshot,
        record: updateRecord(snapshot.record, event, {
          active_stream_id: streamId,
          status: 'active',
        }),
        messages: updatedMessages,
      }
    }
    case 'completion_status': {
      const status = toConversationStatus(payload.status) ?? 'completed'
      const messageStatus = toMessageStatus(payload.status) ?? 'completed'
      const finishedAt = asString(payload.finished_at) ?? event.created_at
      const error = asString(payload.error)
      return {
        ...snapshot,
        record: {
          ...snapshot.record,
          status,
          active_stream_id: null,
          event_seq: event.event_seq,
          updated_at: finishedAt,
        },
        messages: snapshot.messages.map((message) =>
          message.message_id === event.message_id
            ? updateMessageStatus(message, messageStatus, finishedAt, error)
            : message,
        ),
      }
    }
    default:
      return snapshot
  }
}
