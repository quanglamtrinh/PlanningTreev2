import type { ReactNode } from 'react'

import type { NodeRecord } from '../../api/types'
import type { ConversationViewState } from '../../stores/conversation-store'
import type { ConversationSurfaceRequestUi } from '../conversation/components/ConversationSurface.types'
import type { ActiveConversationRequest } from '../conversation/hooks/useConversationRequests'
import { ExecutionConversationPanel } from './ExecutionConversationPanel'

type ExecutionConversationHost = {
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: 'idle' | 'loading_snapshot' | 'error'
  bootstrapError: string | null
  send: (content: string) => Promise<unknown>
  continueFromMessage?: (messageId: string) => Promise<unknown>
  retryFromMessage?: (messageId: string) => Promise<unknown>
  regenerateFromMessage?: (messageId: string) => Promise<unknown>
  cancelStream?: (streamId: string | null) => Promise<unknown>
  activeRequest?: ActiveConversationRequest | null
  requestUi?: ConversationSurfaceRequestUi | null
}

type Props = {
  node: NodeRecord
  composerEnabled?: boolean
  composerPlaceholder?: string
  emptyTitle?: string
  emptyHint?: ReactNode
  executionConversation: ExecutionConversationHost | null
}

export function ChatPanel({
  node,
  composerEnabled,
  composerPlaceholder,
  emptyTitle,
  emptyHint,
  executionConversation,
}: Props) {
  return (
    <ExecutionConversationPanel
      node={node}
      composerEnabled={composerEnabled}
      composerPlaceholder={composerPlaceholder}
      emptyTitle={emptyTitle}
      emptyHint={emptyHint}
      conversationId={executionConversation?.conversationId ?? null}
      conversation={executionConversation?.conversation ?? null}
      bootstrapStatus={executionConversation?.bootstrapStatus ?? 'idle'}
      bootstrapError={executionConversation?.bootstrapError ?? null}
      send={executionConversation?.send ?? (async () => undefined)}
      continueFromMessage={executionConversation?.continueFromMessage}
      retryFromMessage={executionConversation?.retryFromMessage}
      regenerateFromMessage={executionConversation?.regenerateFromMessage}
      cancelStream={executionConversation?.cancelStream}
      activeRequest={executionConversation?.activeRequest}
      requestUi={executionConversation?.requestUi}
    />
  )
}
