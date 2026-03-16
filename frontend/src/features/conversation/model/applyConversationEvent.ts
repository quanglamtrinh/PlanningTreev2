import type {
  ConversationEventEnvelope,
  ConversationEventType,
  ConversationMessage,
  ConversationMessagePart,
  ConversationMessagePartType,
  ConversationMessageStatus,
  ConversationRecord,
  ConversationSnapshot,
  ConversationStatus,
} from '../types'

type PassiveConversationEventType =
  | 'reasoning_state'
  | 'tool_call_start'
  | 'tool_call_update'
  | 'tool_call_finish'
  | 'tool_result'
  | 'plan_block'
  | 'plan_step_status_change'
  | 'diff_summary'
  | 'file_change_summary'

const PASSIVE_EVENT_TO_PART: Record<PassiveConversationEventType, ConversationMessagePartType> = {
  reasoning_state: 'reasoning',
  tool_call_start: 'tool_call',
  tool_call_update: 'tool_call',
  tool_call_finish: 'tool_call',
  tool_result: 'tool_result',
  plan_block: 'plan_block',
  plan_step_status_change: 'plan_step_update',
  diff_summary: 'diff_summary',
  file_change_summary: 'file_change_summary',
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
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

function sortParts(parts: ConversationMessagePart[]): ConversationMessagePart[] {
  return [...parts].sort(
    (left, right) => left.order - right.order || left.part_id.localeCompare(right.part_id),
  )
}

function mergeParts(
  parts: ConversationMessagePart[],
  nextPart: ConversationMessagePart,
): ConversationMessagePart[] {
  const index = parts.findIndex((part) => part.part_id === nextPart.part_id)
  if (index < 0) {
    return sortParts([...parts, nextPart])
  }
  const next = [...parts]
  next[index] = nextPart
  return sortParts(next)
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

function isPassiveConversationEventType(
  eventType: ConversationEventType,
): eventType is PassiveConversationEventType {
  return eventType in PASSIVE_EVENT_TO_PART
}

function findMessageById(
  messages: ConversationMessage[],
  messageId: string | null,
): ConversationMessage | null {
  if (!messageId) {
    return null
  }
  return messages.find((message) => message.message_id === messageId) ?? null
}

function resolvePassiveTargetMessage(
  messages: ConversationMessage[],
  event: ConversationEventEnvelope,
  payload: Record<string, unknown>,
): ConversationMessage | null {
  const explicitMessage =
    findMessageById(messages, asString(event.message_id)) ??
    findMessageById(messages, asString(payload.message_id))
  if (explicitMessage) {
    return explicitMessage
  }

  const turnId = asString(event.turn_id) ?? asString(payload.turn_id)
  if (!turnId) {
    return null
  }

  const assistantMatches = messages.filter(
    (message) => message.turn_id === turnId && message.role === 'assistant',
  )
  if (assistantMatches.length > 0) {
    return assistantMatches[assistantMatches.length - 1] ?? null
  }

  const turnMatches = messages.filter((message) => message.turn_id === turnId)
  if (turnMatches.length === 1) {
    return turnMatches[0] ?? null
  }

  return null
}

function readSemanticSpecificIdentity(
  eventType: PassiveConversationEventType,
  payload: Record<string, unknown>,
): string | null {
  switch (eventType) {
    case 'reasoning_state':
      return asString(payload.reasoning_id)
    case 'tool_call_start':
    case 'tool_call_update':
    case 'tool_call_finish':
      return asString(payload.tool_call_id) ?? asString(payload.call_id)
    case 'tool_result':
      return (
        asString(payload.tool_result_id) ??
        asString(payload.result_for_item_id) ??
        asString(payload.result_for_tool_call_id) ??
        asString(payload.tool_call_id)
      )
    case 'plan_block':
      return asString(payload.plan_id)
    case 'plan_step_status_change':
      return asString(payload.step_id)
    case 'diff_summary':
      return asString(payload.summary_id) ?? asString(payload.diff_id)
    case 'file_change_summary':
      return asString(payload.summary_id) ?? asString(payload.file_id) ?? asString(payload.file_path)
    default:
      return null
  }
}

function buildDeterministicPassivePartId(
  messageId: string,
  partType: ConversationMessagePartType,
  stableIdentity: string,
): string {
  return `${messageId}:${partType}:${stableIdentity}`
}

function findExistingPassivePart(
  parts: ConversationMessagePart[],
  partId: string | null,
  itemKey: string | null,
): ConversationMessagePart | null {
  if (partId) {
    const direct = parts.find((part) => part.part_id === partId)
    if (direct) {
      return direct
    }
  }
  if (itemKey) {
    const keyed = parts.find((part) => part.item_key === itemKey)
    if (keyed) {
      return keyed
    }
  }
  return null
}

function resolvePassivePartTarget(
  message: ConversationMessage,
  event: ConversationEventEnvelope,
  payload: Record<string, unknown>,
  eventType: PassiveConversationEventType,
  partType: ConversationMessagePartType,
): { partId: string; itemKey: string | null; existing: ConversationMessagePart | null } | null {
  const explicitPartId = asString(event.item_id) ?? asString(payload.part_id)
  const semanticKey = readSemanticSpecificIdentity(eventType, payload)
  const stableKey = semanticKey ?? explicitPartId
  if (!explicitPartId && !stableKey) {
    return null
  }

  const resolvedPartId =
    explicitPartId ?? buildDeterministicPassivePartId(message.message_id, partType, stableKey as string)
  const existing = findExistingPassivePart(message.parts, resolvedPartId, stableKey)

  return {
    partId: existing?.part_id ?? resolvedPartId,
    itemKey: existing?.item_key ?? stableKey ?? null,
    existing,
  }
}

function resolvePassiveStatus(
  eventType: PassiveConversationEventType,
  payload: Record<string, unknown>,
): ConversationMessageStatus {
  const explicit = toMessageStatus(payload.status)
  if (explicit) {
    return explicit
  }
  switch (eventType) {
    case 'tool_call_start':
    case 'tool_call_update':
      return 'streaming'
    default:
      return 'completed'
  }
}

function resolvePassiveOrder(
  message: ConversationMessage,
  existing: ConversationMessagePart | null,
  payload: Record<string, unknown>,
): number {
  if (existing) {
    return existing.order
  }
  const explicitOrder = asNumber(payload.order)
  if (explicitOrder !== null) {
    return explicitOrder
  }
  const maxOrder = message.parts.reduce((current, part) => Math.max(current, part.order), -1)
  return maxOrder + 1
}

function copyPayload(payload: Record<string, unknown>): Record<string, unknown> {
  return { ...payload }
}

function upsertPassivePart(
  message: ConversationMessage,
  event: ConversationEventEnvelope,
  partType: ConversationMessagePartType,
  target: { partId: string; itemKey: string | null; existing: ConversationMessagePart | null },
  payload: Record<string, unknown>,
  status: ConversationMessageStatus,
): ConversationMessage {
  const nextPart: ConversationMessagePart = {
    part_id: target.partId,
    part_type: partType,
    status,
    order: resolvePassiveOrder(message, target.existing, payload),
    item_key: target.itemKey,
    created_at: target.existing?.created_at ?? event.created_at,
    updated_at: event.created_at,
    payload: copyPayload(payload),
  }
  return {
    ...message,
    updated_at: event.created_at,
    parts: mergeParts(message.parts, nextPart),
  }
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
    case 'reasoning_state':
    case 'tool_call_start':
    case 'tool_call_update':
    case 'tool_call_finish':
    case 'tool_result':
    case 'plan_block':
    case 'plan_step_status_change':
    case 'diff_summary':
    case 'file_change_summary':
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
        const currentPart = message.parts.find((part) => part.part_id === partId) ?? null
        const nextText = text ?? `${currentPart ? readPartText(currentPart) : ''}${delta}`
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
    default: {
      const passiveEventType = event.event_type
      if (!isPassiveConversationEventType(passiveEventType)) {
        return snapshot
      }

      const partType = PASSIVE_EVENT_TO_PART[passiveEventType]
      const targetMessage = resolvePassiveTargetMessage(snapshot.messages, event, payload)
      if (!targetMessage) {
        return snapshot
      }

      const target = resolvePassivePartTarget(
        targetMessage,
        event,
        payload,
        passiveEventType,
        partType,
      )
      if (!target) {
        return snapshot
      }

      return {
        ...snapshot,
        record: updateRecord(snapshot.record, event, {
          active_stream_id: streamId,
          status: 'active',
        }),
        messages: snapshot.messages.map((message) =>
          message.message_id === targetMessage.message_id
            ? upsertPassivePart(
                message,
                event,
                partType,
                target,
                payload,
                resolvePassiveStatus(passiveEventType, payload),
              )
            : message,
        ),
      }
    }
  }
}
