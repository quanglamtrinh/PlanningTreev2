import { useEffect, useMemo, useRef, useState } from 'react'
import type { KeyboardEvent, ReactNode } from 'react'

import type { NodeRecord } from '../../api/types'
import { useConversationStore, type ConversationViewState } from '../../stores/conversation-store'
import {
  ConversationSurface,
  type ConversationSurfaceConnectionState,
} from '../conversation/components/ConversationSurface'
import type { ConversationSurfaceRequestUi } from '../conversation/components/ConversationSurface.types'
import type { ActiveConversationRequest } from '../conversation/hooks/useConversationRequests'
import { buildConversationRenderModel } from '../conversation/model/buildConversationRenderModel'
import { deriveConversationBusy } from '../conversation/model/deriveConversationBusy'
import { deriveExecutionLineageView } from '../conversation/model/deriveExecutionLineage'

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
  continueFromMessage?: (messageId: string) => Promise<unknown>
  retryFromMessage?: (messageId: string) => Promise<unknown>
  regenerateFromMessage?: (messageId: string) => Promise<unknown>
  cancelStream?: (streamId: string | null) => Promise<unknown>
  activeRequest?: ActiveConversationRequest | null
  requestUi?: ConversationSurfaceRequestUi | null
}

function mapConnectionState(
  bootstrapStatus: BootstrapStatus,
  conversation: ConversationViewState | null,
): ConversationSurfaceConnectionState {
  if (!conversation) {
    return bootstrapStatus === 'error' ? 'error' : 'loading'
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

function readWorkingLabel(snapshot: ConversationViewState['snapshot'] | null | undefined): string | null {
  if (!snapshot) {
    return null
  }

  for (let messageIndex = snapshot.messages.length - 1; messageIndex >= 0; messageIndex -= 1) {
    const message = snapshot.messages[messageIndex]
    for (let partIndex = message.parts.length - 1; partIndex >= 0; partIndex -= 1) {
      const part = message.parts[partIndex]
      if (part.part_type !== 'reasoning') {
        continue
      }
      const payload = part.payload
      const label =
        (typeof payload.summary === 'string' && payload.summary.trim()) ||
        (typeof payload.title === 'string' && payload.title.trim()) ||
        (typeof payload.text === 'string' && payload.text.trim()) ||
        (typeof payload.content === 'string' && payload.content.trim()) ||
        ''
      if (label) {
        return label
      }
    }
  }

  return null
}

function appendQuoteToDraft(currentDraft: string, quote: string): string {
  const trimmedCurrent = currentDraft.trim()
  if (!trimmedCurrent) {
    return `${quote}\n\n`
  }
  const separator = currentDraft.endsWith('\n') ? '\n' : '\n\n'
  return `${currentDraft}${separator}${quote}\n\n`
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
  activeRequest = null,
  requestUi = null,
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

  const streamStartedAtRef = useRef<number | null>(null)
  const [streamStartedAt, setStreamStartedAt] = useState<number | null>(null)
  const [lastDurationMs, setLastDurationMs] = useState<number | null>(null)

  useEffect(() => {
    streamStartedAtRef.current = null
    setStreamStartedAt(null)
    setLastDurationMs(null)
  }, [conversationId])

  useEffect(() => {
    if (!hasConversation) {
      streamStartedAtRef.current = null
      setStreamStartedAt(null)
      setLastDurationMs(null)
      return
    }

    if (isBusy) {
      if (streamStartedAtRef.current === null) {
        const startedAt = Date.now()
        streamStartedAtRef.current = startedAt
        setStreamStartedAt(startedAt)
        setLastDurationMs(null)
      }
      return
    }

    if (streamStartedAtRef.current !== null) {
      setLastDurationMs(Date.now() - streamStartedAtRef.current)
      streamStartedAtRef.current = null
      setStreamStartedAt(null)
    }
  }, [hasConversation, isBusy, conversationId])

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
          eligibility.canContinue && continueFromMessage
            ? {
                key: `continue:${messageId}`,
                label: 'Continue',
                onPress: () => void continueFromMessage(messageId),
              }
            : null,
          eligibility.canRetry && retryFromMessage
            ? {
                key: `retry:${messageId}`,
                label: 'Retry',
                onPress: () => void retryFromMessage(messageId),
              }
            : null,
          eligibility.canRegenerate && regenerateFromMessage
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

  const activeStreamId = hasConversation ? conversation.snapshot.record.active_stream_id : null
  const canStop = Boolean(activeStreamId && cancelStream)
  const workingLabel = readWorkingLabel(conversation?.snapshot)

  return (
    <ConversationSurface
      variant="codex_execution"
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
      canStop={canStop}
      onStop={canStop ? () => void cancelStream?.(activeStreamId) : undefined}
      transcriptStatus={{
        isStreaming: isBusy,
        startedAt: streamStartedAt,
        lastDurationMs,
        workingLabel,
      }}
      activeRequest={activeRequest}
      requestUi={requestUi}
      onQuoteMessage={(quote) => {
        if (!conversationId) {
          return
        }
        setComposerDraft(conversationId, appendQuoteToDraft(composerDraft, quote))
      }}
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
