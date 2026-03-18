import { useMemo } from 'react'
import type { KeyboardEvent } from 'react'

import type { NodeRecord } from '../../api/types'
import { useAskStore } from '../../stores/ask-store'
import { useConversationStore, type ConversationViewState } from '../../stores/conversation-store'
import { useProjectStore } from '../../stores/project-store'
import {
  ConversationSurface,
  type ConversationSurfaceConnectionState,
} from '../conversation/components/ConversationSurface'
import { buildConversationRenderModel } from '../conversation/model/buildConversationRenderModel'
import { deriveConversationBusy } from '../conversation/model/deriveConversationBusy'
import askStyles from './AskPanel.module.css'
import baseStyles from './ChatPanel.module.css'
import { DeltaContextCard } from './DeltaContextCard'

type BootstrapStatus = 'idle' | 'loading_snapshot' | 'error'

type Props = {
  node: NodeRecord
  projectId: string
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: BootstrapStatus
  bootstrapError: string | null
  send: (content: string) => Promise<unknown>
  refresh: () => void
}

type WrapperConnectionState = 'connected' | 'connecting' | 'reconnecting' | 'disconnected'

function ResetIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M3 3v5h5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function defaultComposerHint() {
  return (
    <>
      <kbd>Enter</kbd> to send / <kbd>Shift+Enter</kbd> for new line
    </>
  )
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

function mapWrapperConnectionState(
  connectionState: ConversationSurfaceConnectionState,
): { tone: WrapperConnectionState; label: string } {
  switch (connectionState) {
    case 'connected':
      return { tone: 'connected', label: 'connected' }
    case 'reconnecting':
      return { tone: 'reconnecting', label: 'reconnecting' }
    case 'loading':
      return { tone: 'connecting', label: 'loading' }
    case 'error':
      return { tone: 'disconnected', label: 'error' }
    case 'idle':
      return { tone: 'disconnected', label: 'idle' }
    default:
      return { tone: 'disconnected', label: 'disconnected' }
  }
}

export function AskConversationPanel({
  node,
  projectId,
  conversationId,
  conversation,
  bootstrapStatus,
  bootstrapError,
  send,
  refresh,
}: Props) {
  const snapshot = useProjectStore((state) => state.snapshot)
  const sidecarError = useAskStore((state) => state.error)
  const resetSidecar = useAskStore((state) => state.resetSidecar)
  const askSidecar = useAskStore((state) => state.sidecar)
  const composerDraft = useConversationStore((state) =>
    conversationId ? state.conversationsById[conversationId]?.composerDraft ?? '' : '',
  )
  const setComposerDraft = useConversationStore((state) => state.setComposerDraft)
  const model = useMemo(
    () => buildConversationRenderModel(conversation?.snapshot ?? null),
    [conversation?.snapshot],
  )

  const hasActiveChildren = useMemo(() => {
    if (!snapshot) {
      return false
    }
    const nodeById = new Map(snapshot.tree_state.node_registry.map((item) => [item.node_id, item]))
    return node.child_ids.some((childId) => {
      const child = nodeById.get(childId)
      return Boolean(child && !child.is_superseded)
    })
  }, [node.child_ids, snapshot])

  const connectionState = mapConnectionState(bootstrapStatus, conversation)
  const wrapperConnection = mapWrapperConnectionState(connectionState)
  const hasConversation = conversation !== null && conversationId !== null
  const isBusy = hasConversation ? deriveConversationBusy(conversation.snapshot) : false
  const isLoading = hasConversation
    ? conversation.isLoading === true ||
      conversation.connectionStatus === 'loading_snapshot' ||
      conversation.connectionStatus === 'connecting'
    : bootstrapStatus !== 'error'
  const errorMessage = !hasConversation ? bootstrapError : conversation.error
  const isReadOnly = node.status === 'done' || node.is_superseded
  const composerDisabled =
    isReadOnly ||
    !hasConversation ||
    conversation?.isSending === true ||
    isBusy ||
    connectionState !== 'connected'
  const canReset = hasConversation && !conversation?.isSending && !isBusy && !isReadOnly
  const packetList = askSidecar?.packetList ?? []

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

  async function handleReset() {
    if (!canReset) {
      return
    }
    const confirmed = window.confirm('Reset this ask session and clear all messages?')
    if (!confirmed) {
      return
    }
    try {
      await resetSidecar(projectId, node.node_id)
      if (conversationId) {
        setComposerDraft(conversationId, '')
      }
      refresh()
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

  const placeholder = isReadOnly
    ? 'This ask thread is read-only.'
    : connectionState === 'connected'
      ? `Ask about ${node.title}...`
      : 'Waiting for connection...'

  return (
    <div className={baseStyles.panel}>
      <div className={baseStyles.statusBar}>
        <span className={`${baseStyles.dot} ${baseStyles[wrapperConnection.tone]}`} aria-hidden="true" />
        <span className={baseStyles.statusLabel}>{wrapperConnection.label}</span>
        <span className={baseStyles.nodeLabel}>
          {node.hierarchical_number} / {node.title}
        </span>
        <button
          type="button"
          className={baseStyles.resetBtn}
          disabled={!canReset}
          title="Reset ask session"
          onClick={() => void handleReset()}
        >
          <ResetIcon />
          <span>Reset</span>
        </button>
      </div>

      {sidecarError ? <div className={baseStyles.errorBanner}>{sidecarError}</div> : null}
      {isReadOnly ? (
        <div className={`${askStyles.noticeBanner} ${askStyles.noticeBannerMuted}`}>
          This node is no longer mutable. The ask thread is read-only.
        </div>
      ) : null}
      {hasActiveChildren ? (
        <div className={`${askStyles.noticeBanner} ${askStyles.noticeBannerWarning}`}>
          This node has been split. New packet suggestions on the parent are ignored, and manual packet creation is unavailable.
        </div>
      ) : null}

      <ConversationSurface
        model={model}
        connectionState={connectionState}
        isLoading={isLoading}
        errorMessage={errorMessage}
        contextLabel={`${node.hierarchical_number} / ${node.title}`}
        emptyTitle="Ask a question about this node's plan"
        emptyHint={
          <>
            Explore scope, risks, dependencies, and alternatives for <strong>{node.title}</strong>.
          </>
        }
        showHeader={false}
        showComposer
        composerValue={composerDraft}
        composerDisabled={composerDisabled}
        composerPlaceholder={placeholder}
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

      {packetList.length > 0 ? (
        <div className={askStyles.packetsSection}>
          <h4 className={askStyles.packetsSectionTitle}>Delta Context Packets</h4>
          {packetList.map((packet) => (
            <DeltaContextCard
              key={packet.packet_id}
              packet={packet}
              projectId={projectId}
              nodeId={node.node_id}
              askActive={isBusy}
              planningActive={node.planning_thread_status === 'active'}
              nodeReadOnly={isReadOnly}
              nodeHasActiveChildren={hasActiveChildren}
            />
          ))}
        </div>
      ) : null}
    </div>
  )
}
