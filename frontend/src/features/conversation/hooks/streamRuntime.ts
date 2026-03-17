import {
  evaluateConversationEventAcceptance,
  type ConversationEventAcceptanceDecision,
} from '../model/applyConversationEvent'
import type { ConversationEventEnvelope, ConversationSnapshot } from '../types'
import { useConversationStore } from '../../../stores/conversation-store'

export interface BufferedConversationFlushResult<TEvent extends ConversationEventEnvelope> {
  appliedEvents: TEvent[]
  latestSnapshot: ConversationSnapshot | null
  requiresRecovery: boolean
}

export interface IncomingConversationEventResult {
  decision: ConversationEventAcceptanceDecision
  latestSnapshot: ConversationSnapshot | null
}

export function getAuthoritativeConversationSnapshot(
  conversationId: string,
  fallbackSnapshot: ConversationSnapshot,
): ConversationSnapshot {
  return (
    useConversationStore.getState().conversationsById[conversationId]?.snapshot ?? fallbackSnapshot
  )
}

export function flushBufferedConversationEvents<TEvent extends ConversationEventEnvelope>(
  conversationId: string,
  bufferedEvents: TEvent[],
): BufferedConversationFlushResult<TEvent> {
  const appliedEvents: TEvent[] = []
  let requiresRecovery = false

  for (const event of [...bufferedEvents].sort((left, right) => left.event_seq - right.event_seq)) {
    const current = useConversationStore.getState().conversationsById[conversationId]
    if (!current) {
      bufferedEvents.length = 0
      return {
        appliedEvents,
        latestSnapshot: null,
        requiresRecovery,
      }
    }

    const acceptance = evaluateConversationEventAcceptance(current.snapshot, event)
    if (acceptance.decision === 'recover') {
      requiresRecovery = true
      break
    }
    if (acceptance.decision !== 'accept') {
      continue
    }

    useConversationStore.getState().applyEvent(conversationId, event)
    appliedEvents.push(event)
  }

  bufferedEvents.length = 0

  return {
    appliedEvents,
    latestSnapshot: useConversationStore.getState().conversationsById[conversationId]?.snapshot ?? null,
    requiresRecovery,
  }
}

export function applyIncomingConversationEvent<TEvent extends ConversationEventEnvelope>(
  conversationId: string,
  event: TEvent,
): IncomingConversationEventResult {
  const current = useConversationStore.getState().conversationsById[conversationId]
  if (!current) {
    return {
      decision: 'ignore',
      latestSnapshot: null,
    }
  }

  const acceptance = evaluateConversationEventAcceptance(current.snapshot, event)
  if (acceptance.decision === 'accept') {
    useConversationStore.getState().applyEvent(conversationId, event)
  }

  return {
    decision: acceptance.decision,
    latestSnapshot: useConversationStore.getState().conversationsById[conversationId]?.snapshot ?? null,
  }
}
