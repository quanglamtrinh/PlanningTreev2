import type { AgentActivity, NodeDocuments, NodeRecord } from '../../api/types'
import type { ConversationViewState } from '../../stores/conversation-store'
import { LegacyPlanningPanel } from './LegacyPlanningPanel'
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
  planningConversation?: PlanningConversationHost | null
}

export function PlanningPanel({
  node,
  documents,
  activity,
  planningConversation,
}: Props) {
  if (planningConversation) {
    return (
      <PlanningConversationPanel
        node={node}
        documents={documents}
        activity={activity}
        conversationId={planningConversation.conversationId}
        conversation={planningConversation.conversation}
        bootstrapStatus={planningConversation.bootstrapStatus}
        bootstrapError={planningConversation.bootstrapError}
      />
    )
  }

  return <LegacyPlanningPanel node={node} documents={documents} activity={activity} />
}
