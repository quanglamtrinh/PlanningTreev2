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

type InteractiveConversationEventType =
  | 'approval_request'
  | 'request_user_input'
  | 'request_resolved'
  | 'user_input_resolved'

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

const INTERACTIVE_EVENT_TO_PART: Record<
  Exclude<InteractiveConversationEventType, 'request_resolved'>,
  ConversationMessagePartType
> = {
  approval_request: 'approval_request',
  request_user_input: 'user_input_request',
  user_input_resolved: 'user_input_response',
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

function isInteractiveConversationEventType(
  eventType: ConversationEventType,
): eventType is InteractiveConversationEventType {
  return (
    eventType === 'approval_request' ||
    eventType === 'request_user_input' ||
    eventType === 'request_resolved' ||
    eventType === 'user_input_resolved'
  )
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

type PassiveTargetMessageResolution =
  | { message: ConversationMessage; reason: null }
  | { message: null; reason: string }

function resolvePassiveTargetMessage(
  messages: ConversationMessage[],
  event: ConversationEventEnvelope,
  payload: Record<string, unknown>,
): PassiveTargetMessageResolution {
  const explicitEventMessage = findMessageById(messages, asString(event.message_id))
  if (explicitEventMessage) {
    if (explicitEventMessage.role !== 'assistant') {
      return {
        message: null,
        reason: 'explicit_message_not_assistant',
      }
    }
    return {
      message: explicitEventMessage,
      reason: null,
    }
  }

  const explicitPayloadMessage = findMessageById(messages, asString(payload.message_id))
  if (explicitPayloadMessage) {
    if (explicitPayloadMessage.role !== 'assistant') {
      return {
        message: null,
        reason: 'payload_message_not_assistant',
      }
    }
    return {
      message: explicitPayloadMessage,
      reason: null,
    }
  }

  const turnId = asString(event.turn_id) ?? asString(payload.turn_id)
  if (!turnId) {
    return {
      message: null,
      reason: 'missing_target_message',
    }
  }

  const assistantMatches = messages.filter(
    (message) => message.turn_id === turnId && message.role === 'assistant',
  )
  if (assistantMatches.length > 0) {
    return {
      message: assistantMatches[assistantMatches.length - 1] ?? null,
      reason: null,
    }
  }

  return {
    message: null,
    reason: 'missing_assistant_target_for_turn',
  }
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

function readResolutionState(payload: Record<string, unknown>): string | null {
  return asString(payload.resolution_state)
}

function resolveInteractiveStatusFromPayload(
  payload: Record<string, unknown>,
): ConversationMessageStatus {
  const explicit = toMessageStatus(payload.status)
  if (explicit) {
    return explicit
  }
  switch (readResolutionState(payload)) {
    case 'resolved':
    case 'approved':
    case 'declined':
      return 'completed'
    case 'stale':
    case 'cancelled':
      return 'cancelled'
    case 'error':
      return 'error'
    default:
      return 'pending'
  }
}

function reportDroppedPassiveUpdate(
  reason: string,
  event: ConversationEventEnvelope,
  payload: Record<string, unknown>,
) {
  if (typeof console === 'undefined' || typeof console.warn !== 'function') {
    return
  }
  console.warn('[conversation] dropped passive event', {
    reason,
    eventType: event.event_type,
    conversationId: event.conversation_id,
    streamId: readEventStreamId(event),
    eventSeq: event.event_seq,
    messageId: asString(event.message_id) ?? asString(payload.message_id),
    turnId: asString(event.turn_id) ?? asString(payload.turn_id),
    itemId: asString(event.item_id) ?? asString(payload.part_id),
  })
}

function reportDroppedInteractiveUpdate(
  reason: string,
  event: ConversationEventEnvelope,
  payload: Record<string, unknown>,
) {
  if (typeof console === 'undefined' || typeof console.warn !== 'function') {
    return
  }
  console.warn('[conversation] dropped interactive event', {
    reason,
    eventType: event.event_type,
    conversationId: event.conversation_id,
    streamId: readEventStreamId(event),
    eventSeq: event.event_seq,
    messageId: asString(event.message_id) ?? asString(payload.message_id),
    requestId: asString(payload.request_id),
    turnId: asString(event.turn_id) ?? asString(payload.turn_id),
    itemId: asString(event.item_id) ?? asString(payload.part_id),
  })
}

function readConversationMessage(payload: Record<string, unknown>): ConversationMessage | null {
  const message = payload.message
  if (!message || typeof message !== 'object' || Array.isArray(message)) {
    return null
  }
  return message as ConversationMessage
}

function resolveRequestPartType(
  payload: Record<string, unknown>,
  existingPart: ConversationMessagePart | null,
): ConversationMessagePartType | null {
  if (existingPart) {
    return existingPart.part_type
  }
  const requestKind = asString(payload.request_kind)
  if (requestKind === 'approval') {
    return 'approval_request'
  }
  if (requestKind === 'user_input') {
    return 'user_input_request'
  }
  return null
}

function findRequestTarget(
  messages: ConversationMessage[],
  payload: Record<string, unknown>,
  event: ConversationEventEnvelope,
): { message: ConversationMessage; part: ConversationMessagePart } | null {
  const explicitMessageId = asString(event.message_id) ?? asString(payload.message_id)
  const explicitPartId = asString(event.item_id) ?? asString(payload.part_id)
  const requestId = asString(payload.request_id)

  if (explicitMessageId && explicitPartId) {
    const message = messages.find((candidate) => candidate.message_id === explicitMessageId) ?? null
    const part = message?.parts.find((candidate) => candidate.part_id === explicitPartId) ?? null
    if (message && part) {
      return { message, part }
    }
  }

  if (explicitPartId) {
    for (const message of messages) {
      const part = message.parts.find((candidate) => candidate.part_id === explicitPartId) ?? null
      if (part) {
        return { message, part }
      }
    }
  }

  if (requestId) {
    const matches: Array<{ message: ConversationMessage; part: ConversationMessagePart }> = []
    for (const message of messages) {
      for (const part of message.parts) {
        if (
          (part.part_type === 'approval_request' || part.part_type === 'user_input_request') &&
          asString(part.payload.request_id) === requestId
        ) {
          matches.push({ message, part })
        }
      }
    }
    if (matches.length === 1) {
      return matches[0] ?? null
    }
  }

  return null
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

function upsertInteractivePart(
  message: ConversationMessage,
  partType: ConversationMessagePartType,
  partId: string,
  payload: Record<string, unknown>,
  updatedAt: string,
): ConversationMessage {
  const existing = message.parts.find((part) => part.part_id === partId) ?? null
  const nextStatus = resolveInteractiveStatusFromPayload(payload)
  const nextPart: ConversationMessagePart = {
    part_id: partId,
    part_type: partType,
    status: nextStatus,
    order: existing?.order ?? (asNumber(payload.order) ?? message.parts.length),
    item_key: existing?.item_key ?? asString(payload.request_id) ?? null,
    created_at: existing?.created_at ?? updatedAt,
    updated_at: updatedAt,
    payload: copyPayload(payload),
  }
  return {
    ...message,
    status: nextStatus,
    updated_at: updatedAt,
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
    case 'approval_request':
    case 'request_user_input':
    case 'request_resolved':
    case 'user_input_resolved':
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
    case 'approval_request':
    case 'request_user_input':
    case 'user_input_resolved': {
      const message = readConversationMessage(payload)
      if (!message) {
        reportDroppedInteractiveUpdate('missing_message_payload', event, payload)
        return snapshot
      }
      const partType = INTERACTIVE_EVENT_TO_PART[event.event_type]
      const nextMessage =
        partType === 'user_input_response'
          ? {
              ...message,
              status: message.status ?? resolveInteractiveStatusFromPayload(payload),
            }
          : message
      return {
        ...snapshot,
        record: updateRecord(snapshot.record, event, {
          active_stream_id: streamId,
          status: 'active',
        }),
        messages: mergeMessages(snapshot.messages, nextMessage),
      }
    }
    case 'request_resolved': {
      const target = findRequestTarget(snapshot.messages, payload, event)
      if (!target) {
        reportDroppedInteractiveUpdate('missing_request_target', event, payload)
        return snapshot
      }
      const partType = resolveRequestPartType(payload, target.part)
      if (!partType) {
        reportDroppedInteractiveUpdate('missing_request_kind', event, payload)
        return snapshot
      }
      return {
        ...snapshot,
        record: updateRecord(snapshot.record, event, {
          active_stream_id: streamId,
          status: 'active',
        }),
        messages: snapshot.messages.map((message) =>
          message.message_id === target.message.message_id
            ? upsertInteractivePart(
                message,
                partType,
                target.part.part_id,
                {
                  ...target.part.payload,
                  ...copyPayload(payload),
                  part_id: target.part.part_id,
                },
                event.created_at,
              )
            : message,
        ),
      }
    }
    default: {
      const passiveEventType = event.event_type
      if (!isPassiveConversationEventType(passiveEventType)) {
        if (isInteractiveConversationEventType(passiveEventType)) {
          return snapshot
        }
        return snapshot
      }

      const partType = PASSIVE_EVENT_TO_PART[passiveEventType]
      const targetMessageResolution = resolvePassiveTargetMessage(snapshot.messages, event, payload)
      if (!targetMessageResolution.message) {
        reportDroppedPassiveUpdate(targetMessageResolution.reason, event, payload)
        return snapshot
      }
      const targetMessage = targetMessageResolution.message

      const target = resolvePassivePartTarget(
        targetMessage,
        event,
        payload,
        passiveEventType,
        partType,
      )
      if (!target) {
        reportDroppedPassiveUpdate('missing_target_part', event, payload)
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
