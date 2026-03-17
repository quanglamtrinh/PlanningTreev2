import { useMemo } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

import type { NodeRecord } from '../../api/types'
import { ConversationSurface, type ConversationSurfaceConnectionState } from '../conversation/components/ConversationSurface'
import { buildConversationRenderModel } from '../conversation/model/buildConversationRenderModel'
import { deriveExecutionLineageView } from '../conversation/model/deriveExecutionLineage'
import { deriveConversationBusy } from '../conversation/model/deriveConversationBusy'
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
  continueFromMessage: (messageId: string) => Promise<unknown>
  retryFromMessage: (messageId: string) => Promise<unknown>
  regenerateFromMessage: (messageId: string) => Promise<unknown>
  cancelStream: (streamId: string | null) => Promise<unknown>
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
  continueFromMessage,
  retryFromMessage,
  regenerateFromMessage,
  cancelStream,
}: Props) {
  const composerDraft = useConversationStore((state) =>
    conversationId ? state.conversationsById[conversationId]?.composerDraft ?? '' : '',
  )
  const setComposerDraft = useConversationStore((state) => state.setComposerDraft)
  const model = useMemo(
    () => buildConversationRenderModel(conversation?.snapshot ?? null),
    [conversation?.snapshot],
  )
  const lineageView = useMemo(
    () => deriveExecutionLineageView(conversation?.snapshot ?? null),
    [conversation?.snapshot],
  )

  const connectionState = mapConnectionState(bootstrapStatus, conversation)
  const hasConversation = conversation !== null && conversationId !== null
  const isBusy = hasConversation ? deriveConversationBusy(conversation.snapshot) : false
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

  const messageActions = useMemo(() => {
    if (!lineageView) {
      return {}
    }
    return Object.fromEntries(
      Object.entries(lineageView.actionEligibilityByMessageId).map(([messageId, eligibility]) => {
        const actions = [
          eligibility.canContinue
            ? {
                key: `continue:${messageId}`,
                label: 'Continue',
                onPress: () => void continueFromMessage(messageId),
              }
            : null,
          eligibility.canRetry
            ? {
                key: `retry:${messageId}`,
                label: 'Retry',
                onPress: () => void retryFromMessage(messageId),
              }
            : null,
          eligibility.canRegenerate
            ? {
                key: `regenerate:${messageId}`,
                label: 'Regenerate',
                onPress: () => void regenerateFromMessage(messageId),
              }
            : null,
        ].filter((value): value is NonNullable<typeof value> => value !== null)
        return [messageId, actions]
      }),
    )
  }, [continueFromMessage, lineageView, regenerateFromMessage, retryFromMessage])

  const streamAction =
    hasConversation && conversation.snapshot.record.active_stream_id
      ? {
          label: 'Cancel',
          onPress: () => void cancelStream(conversation.snapshot.record.active_stream_id),
        }
      : null

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
      messageActions={messageActions}
      streamAction={streamAction}
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
