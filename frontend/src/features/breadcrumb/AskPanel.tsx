import type { NodeRecord } from '../../api/types'
import type { ConversationViewState } from '../../stores/conversation-store'
import { AskConversationPanel } from './AskConversationPanel'

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
  askConversation: AskConversationHost | null
}

export function AskPanel({ node, projectId, askConversation }: Props) {
  return (
    <AskConversationPanel
      node={node}
      projectId={projectId}
      conversationId={askConversation?.conversationId ?? null}
      conversation={askConversation?.conversation ?? null}
      bootstrapStatus={askConversation?.bootstrapStatus ?? 'idle'}
      bootstrapError={askConversation?.bootstrapError ?? null}
      send={askConversation?.send ?? (async () => undefined)}
      refresh={askConversation?.refresh ?? (() => undefined)}
    />
  )
}
