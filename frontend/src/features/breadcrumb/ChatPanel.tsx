import type { ReactNode } from 'react'

import type { NodeRecord } from '../../api/types'
import type { ConversationViewState } from '../../stores/conversation-store'
import { ExecutionConversationPanel } from './ExecutionConversationPanel'
import { LegacyExecutionChatPanel } from './LegacyExecutionChatPanel'

type ExecutionConversationHost = {
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: 'idle' | 'loading_snapshot' | 'error'
  bootstrapError: string | null
  send: (content: string) => Promise<unknown>
  continueFromMessage: (messageId: string) => Promise<unknown>
  retryFromMessage: (messageId: string) => Promise<unknown>
  regenerateFromMessage: (messageId: string) => Promise<unknown>
  cancelStream: (streamId: string | null) => Promise<unknown>
}

type Props = {
  node: NodeRecord
  projectId: string
  composerEnabled?: boolean
  composerPlaceholder?: string
  emptyTitle?: string
  emptyHint?: ReactNode
  executionConversation?: ExecutionConversationHost | null
}

export function ChatPanel({
  node,
  projectId,
  composerEnabled,
  composerPlaceholder,
  emptyTitle,
  emptyHint,
  executionConversation,
}: Props) {
  if (executionConversation) {
    return (
      <ExecutionConversationPanel
        node={node}
        composerEnabled={composerEnabled}
        composerPlaceholder={composerPlaceholder}
        emptyTitle={emptyTitle}
        emptyHint={emptyHint}
        conversationId={executionConversation.conversationId}
        conversation={executionConversation.conversation}
        bootstrapStatus={executionConversation.bootstrapStatus}
        bootstrapError={executionConversation.bootstrapError}
        send={executionConversation.send}
        continueFromMessage={executionConversation.continueFromMessage}
        retryFromMessage={executionConversation.retryFromMessage}
        regenerateFromMessage={executionConversation.regenerateFromMessage}
        cancelStream={executionConversation.cancelStream}
      />
    )
  }

  return (
    <LegacyExecutionChatPanel
      node={node}
      projectId={projectId}
      composerEnabled={composerEnabled}
      composerPlaceholder={composerPlaceholder}
      emptyTitle={emptyTitle}
      emptyHint={emptyHint}
    />
  )
}
