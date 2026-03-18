import type { AgentActivity, NodeDocuments, NodeRecord } from '../../api/types'
import type { ConversationViewState } from '../../stores/conversation-store'
import { PlanningConversationPanel } from './PlanningConversationPanel'

type PlanningConversationHost = {
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: 'idle' | 'loading_snapshot' | 'error'
  bootstrapError: string | null
}

type Props = {
  node: NodeRecord
  documents?: NodeDocuments
  activity?: AgentActivity
  planningConversation: PlanningConversationHost | null
}

export function PlanningPanel({
  node,
  documents,
  activity,
  planningConversation,
}: Props) {
  return (
    <PlanningConversationPanel
      node={node}
      documents={documents}
      activity={activity}
      conversationId={planningConversation?.conversationId ?? null}
      conversation={planningConversation?.conversation ?? null}
      bootstrapStatus={planningConversation?.bootstrapStatus ?? 'idle'}
      bootstrapError={planningConversation?.bootstrapError ?? null}
    />
  )
}
