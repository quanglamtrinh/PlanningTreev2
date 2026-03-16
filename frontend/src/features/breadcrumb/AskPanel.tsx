import type { NodeRecord } from '../../api/types'
import type { ConversationViewState } from '../../stores/conversation-store'
import { AskConversationPanel } from './AskConversationPanel'
import { LegacyAskPanel } from './LegacyAskPanel'

type AskConversationHost = {
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: 'idle' | 'loading_snapshot' | 'error'
  bootstrapError: string | null
  send: (content: string) => Promise<unknown>
  refresh: () => void
}

type Props = {
  node: NodeRecord
  projectId: string
  askConversation?: AskConversationHost | null
}

export function AskPanel({ node, projectId, askConversation }: Props) {
  if (askConversation) {
    return (
      <AskConversationPanel
        node={node}
        projectId={projectId}
        conversationId={askConversation.conversationId}
        conversation={askConversation.conversation}
        bootstrapStatus={askConversation.bootstrapStatus}
        bootstrapError={askConversation.bootstrapError}
        send={askConversation.send}
        refresh={askConversation.refresh}
      />
    )
  }

  return <LegacyAskPanel node={node} projectId={projectId} />
}
