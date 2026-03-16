import { useMemo } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

import type { NodeRecord } from '../../api/types'
import { ConversationSurface, type ConversationSurfaceConnectionState } from '../conversation/components/ConversationSurface'
import { buildConversationRenderModel } from '../conversation/model/buildConversationRenderModel'
import { deriveExecutionBusy } from '../conversation/model/deriveExecutionBusy'
import { useConversationStore, type ConversationViewState } from '../../stores/conversation-store'

type BootstrapStatus = 'idle' | 'loading_snapshot' | 'error'

type Props = {
  node: NodeRecord
  composerEnabled?: boolean
  composerPlaceholder?: string
  emptyTitle?: string
  emptyHint?: ReactNode
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: BootstrapStatus
  bootstrapError: string | null
  send: (content: string) => Promise<unknown>
}

function mapConnectionState(
  bootstrapStatus: BootstrapStatus,
  conversation: ConversationViewState | null,
): ConversationSurfaceConnectionState {
  if (!conversation) {
    if (bootstrapStatus === 'error') {
      return 'error'
    }
    return 'loading'
  }

  if (bootstrapStatus === 'error' || conversation.connectionStatus === 'error') {
    return 'error'
  }
  if (
    bootstrapStatus === 'loading_snapshot' ||
    conversation.connectionStatus === 'loading_snapshot' ||
    conversation.connectionStatus === 'connecting'
  ) {
    return 'loading'
  }
  if (conversation.connectionStatus === 'connected') {
    return 'connected'
  }
  if (conversation.connectionStatus === 'reconnecting') {
    return 'reconnecting'
  }
  if (conversation.connectionStatus === 'disconnected') {
    return 'disconnected'
  }
  return 'idle'
}

function defaultComposerHint() {
  return (
    <>
      <kbd>Enter</kbd> to send / <kbd>Shift+Enter</kbd> for new line
    </>
  )
}

export function ExecutionConversationPanel({
  node,
  composerEnabled = true,
  composerPlaceholder = 'Write a message...',
  emptyTitle = 'Execution Conversation',
  emptyHint,
  conversationId,
  conversation,
  bootstrapStatus,
  bootstrapError,
  send,
}: Props) {
  const composerDraft = useConversationStore((state) =>
    conversationId ? state.conversationsById[conversationId]?.composerDraft ?? '' : '',
  )
  const setComposerDraft = useConversationStore((state) => state.setComposerDraft)
  const model = useMemo(
    () => buildConversationRenderModel(conversation?.snapshot ?? null),
    [conversation?.snapshot],
  )

  const connectionState = mapConnectionState(bootstrapStatus, conversation)
  const hasConversation = conversation !== null && conversationId !== null
  const isBusy = hasConversation ? deriveExecutionBusy(conversation.snapshot) : false
  const isLoading = hasConversation
    ? conversation.isLoading === true ||
      conversation.connectionStatus === 'loading_snapshot' ||
      conversation.connectionStatus === 'connecting'
    : bootstrapStatus !== 'error'
  const errorMessage = !hasConversation ? bootstrapError : conversation.error
  const composerDisabled =
    !composerEnabled ||
    !hasConversation ||
    conversation?.isSending === true ||
    isBusy ||
    connectionState !== 'connected'

  async function handleSend() {
    const activeConversationId = conversationId
    const draft = composerDraft.trim()
    if (!activeConversationId || !draft || composerDisabled) {
      return
    }
    try {
      await send(draft)
      setComposerDraft(activeConversationId, '')
    } catch {
      return
    }
  }

  function handleComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void handleSend()
    }
  }

  return (
    <ConversationSurface
      model={model}
      connectionState={connectionState}
      isLoading={isLoading}
      errorMessage={errorMessage}
      contextLabel={`${node.hierarchical_number} / ${node.title}`}
      emptyTitle={emptyTitle}
      emptyHint={
        emptyHint ?? (
          <>
            Messages from the current execution run will appear here for <strong>{node.title}</strong>.
          </>
        )
      }
      showComposer
      composerValue={composerDraft}
      composerDisabled={composerDisabled}
      composerPlaceholder={composerPlaceholder}
      composerHint={defaultComposerHint()}
      onComposerValueChange={(draft) => {
        if (!conversationId) {
          return
        }
        setComposerDraft(conversationId, draft)
      }}
      onComposerSubmit={() => void handleSend()}
      onComposerKeyDown={handleComposerKeyDown}
    />
  )
}
