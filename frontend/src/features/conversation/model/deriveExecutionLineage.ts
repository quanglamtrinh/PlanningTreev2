import type { ConversationMessage, ConversationSnapshot } from '../types'

const VISIBLE_EXECUTION_HEAD_STATUSES = new Set([
  'pending',
  'streaming',
  'completed',
  'error',
  'interrupted',
  'cancelled',
])

export interface ExecutionReplayGroup {
  key: string
  anchorMessageId: string | null
  firstMessageId: string
  messages: ConversationMessage[]
}

export interface ExecutionLineageActionEligibility {
  canContinue: boolean
  canRetry: boolean
  canRegenerate: boolean
}

export interface ExecutionLineageView {
  visibleHeadId: string | null
  visibleMessageIds: Set<string>
  visibleMessages: ConversationMessage[]
  replayGroups: ExecutionReplayGroup[]
  actionEligibilityByMessageId: Record<string, ExecutionLineageActionEligibility>
  canCancel: boolean
}

function hasPartType(message: ConversationMessage, partType: string): boolean {
  return message.parts.some((part) => part.part_type === partType)
}

function isExecutionAssistantHeadCandidate(message: ConversationMessage): boolean {
  if (message.role !== 'assistant') {
    return false
  }
  if (message.runtime_mode !== 'execute') {
    return false
  }
  if (!hasPartType(message, 'assistant_text')) {
    return false
  }
  if (!VISIBLE_EXECUTION_HEAD_STATUSES.has(message.status)) {
    return false
  }
  if (message.status === 'superseded') {
    return false
  }
  return !message.lineage.superseded_by_message_id
}

function findVisibleHead(messages: ConversationMessage[]): ConversationMessage | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (isExecutionAssistantHeadCandidate(message)) {
      return message
    }
  }
  return null
}

function collectVisibleMessageIds(messages: ConversationMessage[]): Set<string> {
  const visibleHead = findVisibleHead(messages)
  if (!visibleHead) {
    return new Set()
  }
  const messageById = new Map(messages.map((message) => [message.message_id, message]))
  const lineageMessageIds = new Set<string>()
  let cursor: ConversationMessage | null = visibleHead
  while (cursor) {
    if (lineageMessageIds.has(cursor.message_id)) {
      break
    }
    lineageMessageIds.add(cursor.message_id)
    const parentId: string | null = cursor.lineage.parent_message_id ?? null
    cursor = parentId ? messageById.get(parentId) ?? null : null
  }
  const visibleTurnIds = new Set(
    messages
      .filter((message) => lineageMessageIds.has(message.message_id))
      .map((message) => message.turn_id),
  )
  return new Set(
    messages.flatMap((message) => {
      if (lineageMessageIds.has(message.message_id)) {
        return [message.message_id]
      }
      if (!visibleTurnIds.has(message.turn_id)) {
        return []
      }
      if (hasPartType(message, 'assistant_text')) {
        return []
      }
      return [message.message_id]
    }),
  )
}

function resolveReplayAnchorMessageId(
  message: ConversationMessage,
  messageById: Map<string, ConversationMessage>,
  visibleMessageIds: Set<string>,
): string | null {
  const visited = new Set<string>()
  let cursor: ConversationMessage | null = message
  while (cursor) {
    if (visited.has(cursor.message_id)) {
      return null
    }
    visited.add(cursor.message_id)
    if (cursor.lineage.superseded_by_message_id) {
      return cursor.message_id
    }
    const parentId: string | null = cursor.lineage.parent_message_id ?? null
    if (!parentId) {
      return null
    }
    if (visibleMessageIds.has(parentId)) {
      return parentId
    }
    cursor = messageById.get(parentId) ?? null
  }
  return null
}

function buildReplayGroups(
  messages: ConversationMessage[],
  visibleMessageIds: Set<string>,
): ExecutionReplayGroup[] {
  const messageById = new Map(messages.map((message) => [message.message_id, message]))
  const groups = new Map<string, ExecutionReplayGroup>()
  for (const message of messages) {
    if (visibleMessageIds.has(message.message_id)) {
      continue
    }
    const anchorMessageId = resolveReplayAnchorMessageId(message, messageById, visibleMessageIds)
    const groupKey = anchorMessageId ? `replay:${anchorMessageId}` : `replay:root:${message.message_id}`
    const existing = groups.get(groupKey)
    if (existing) {
      existing.messages.push(message)
      continue
    }
    groups.set(groupKey, {
      key: groupKey,
      anchorMessageId,
      firstMessageId: message.message_id,
      messages: [message],
    })
  }
  return [...groups.values()]
}

function buildActionEligibility(
  visibleMessages: ConversationMessage[],
  canCancel: boolean,
): Record<string, ExecutionLineageActionEligibility> {
  const latestCompletedAssistant = [...visibleMessages]
    .reverse()
    .find((message) => isExecutionAssistantHeadCandidate(message) && message.status === 'completed')
  const latestFailedAssistant = [...visibleMessages]
    .reverse()
    .find(
      (message) =>
        isExecutionAssistantHeadCandidate(message) &&
        (message.status === 'error' ||
          message.status === 'interrupted' ||
          message.status === 'cancelled'),
    )

  const eligibilityByMessageId: Record<string, ExecutionLineageActionEligibility> = {}
  for (const message of visibleMessages) {
    eligibilityByMessageId[message.message_id] = {
      canContinue: !canCancel && latestCompletedAssistant?.message_id === message.message_id,
      canRetry: !canCancel && latestFailedAssistant?.message_id === message.message_id,
      canRegenerate: !canCancel && latestCompletedAssistant?.message_id === message.message_id,
    }
  }
  return eligibilityByMessageId
}

export function deriveExecutionLineageView(
  snapshot: ConversationSnapshot | null | undefined,
): ExecutionLineageView | null {
  if (!snapshot || snapshot.record.thread_type !== 'execution') {
    return null
  }

  const visibleMessageIds = collectVisibleMessageIds(snapshot.messages)
  if (visibleMessageIds.size === 0) {
    const visibleMessages = snapshot.messages
    return {
      visibleHeadId: null,
      visibleMessageIds: new Set(visibleMessages.map((message) => message.message_id)),
      visibleMessages,
      replayGroups: [],
      actionEligibilityByMessageId: buildActionEligibility(visibleMessages, snapshot.record.active_stream_id !== null),
      canCancel: snapshot.record.active_stream_id !== null,
    }
  }
  const visibleMessages = snapshot.messages.filter((message) => visibleMessageIds.has(message.message_id))
  const replayGroups = buildReplayGroups(snapshot.messages, visibleMessageIds)
  const visibleHeadId = findVisibleHead(snapshot.messages)?.message_id ?? null
  const canCancel = snapshot.record.active_stream_id !== null

  return {
    visibleHeadId,
    visibleMessageIds,
    visibleMessages,
    replayGroups,
    actionEligibilityByMessageId: buildActionEligibility(visibleMessages, canCancel),
    canCancel,
  }
}
