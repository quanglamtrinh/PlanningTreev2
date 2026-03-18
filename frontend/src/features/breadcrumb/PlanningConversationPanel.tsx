import { useMemo } from 'react'

import type { AgentActivity, NodeDocuments, NodeRecord } from '../../api/types'
import { useProjectStore } from '../../stores/project-store'
import { type ConversationViewState } from '../../stores/conversation-store'
import {
  ConversationSurface,
  type ConversationSurfaceConnectionState,
} from '../conversation/components/ConversationSurface'
import { buildConversationRenderModel } from '../conversation/model/buildConversationRenderModel'
import { deriveConversationBusy } from '../conversation/model/deriveConversationBusy'
import { AgentActivityCard } from './AgentActivityCard'
import styles from './PlanningPanel.module.css'

type BootstrapStatus = 'idle' | 'loading_snapshot' | 'error'

type Props = {
  node: NodeRecord
  documents?: NodeDocuments
  activity?: AgentActivity
  conversationId: string | null
  conversation: ConversationViewState | null
  bootstrapStatus: BootstrapStatus
  bootstrapError: string | null
}

type WrapperConnectionState = 'connected' | 'connecting' | 'reconnecting' | 'disconnected'

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

export function PlanningConversationPanel({
  node,
  documents,
  activity,
  conversationId,
  conversation,
  bootstrapStatus,
  bootstrapError,
}: Props) {
  const splitNode = useProjectStore((state) => state.splitNode)
  const snapshot = useProjectStore((state) => state.snapshot)
  const isSplittingNode = useProjectStore((state) => state.isSplittingNode)
  const splittingNodeId = useProjectStore((state) => state.splittingNodeId)
  const model = useMemo(
    () => buildConversationRenderModel(conversation?.snapshot ?? null),
    [conversation?.snapshot],
  )

  const activeChildren = useMemo(() => {
    if (!snapshot) {
      return []
    }
    return node.child_ids
      .map((childId) => snapshot.tree_state.node_registry.find((item) => item.node_id === childId) ?? null)
      .filter((child) => Boolean(child && !child.is_superseded))
  }, [node.child_ids, snapshot])

  const hasLivePlanningConversationActivity = deriveConversationBusy(conversation?.snapshot)
  const optimisticBusy = isSplittingNode && splittingNodeId === node.node_id
  const isBusy = hasLivePlanningConversationActivity || optimisticBusy
  const connectionState = mapConnectionState(bootstrapStatus, conversation)
  const wrapperConnection = mapWrapperConnectionState(connectionState)
  const hasConversation = conversation !== null && conversationId !== null
  const isLoading = hasConversation
    ? conversation.isLoading === true ||
      conversation.connectionStatus === 'loading_snapshot' ||
      conversation.connectionStatus === 'connecting'
    : bootstrapStatus !== 'error'
  const errorMessage = !hasConversation ? bootstrapError : conversation.error
  const canSplit = !isBusy && !node.is_superseded && node.status !== 'done'

  const splitFailure = documents?.state?.last_agent_failure?.operation === 'split'
    ? documents.state.last_agent_failure
    : null
  const splitActivityCard = splitFailure ? (
    <AgentActivityCard
      title="Planning Activity"
      status="Failed"
      tone="negative"
      message={splitFailure.message || 'The split operation did not complete.'}
    />
  ) : activity?.operation === 'split' ? (
    <AgentActivityCard
      title="Planning Activity"
      status={
        activity.status === 'operation_completed'
          ? 'Completed'
          : activity.status === 'operation_failed'
            ? 'Failed'
            : activity.stage === 'preparing'
              ? 'Preparing'
              : 'Planning'
      }
      tone={
        activity.status === 'operation_completed'
          ? 'positive'
          : activity.status === 'operation_failed'
            ? 'negative'
            : 'neutral'
      }
      message={
        activity.message ||
        (isBusy ? 'The planner is preparing a split for this node.' : 'Split activity is idle.')
      }
    />
  ) : isBusy ? (
    <AgentActivityCard
      title="Planning Activity"
      status="Preparing"
      message="The planner is preparing a split for this node."
    />
  ) : null

  async function handleSplit(mode: 'walking_skeleton' | 'slice') {
    let confirmReplace = false
    if (activeChildren.length > 0) {
      confirmReplace = window.confirm("This will replace the node's current active children. Continue?")
      if (!confirmReplace) {
        return
      }
    }
    try {
      await splitNode(node.node_id, mode, confirmReplace)
    } catch {
      return
    }
  }

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <div>
          <p className={styles.kicker}>Planning Thread</p>
          <h3 className={styles.title}>
            {node.hierarchical_number} / {node.title}
          </h3>
          <p className={styles.copy}>{node.description || 'No description yet.'}</p>
        </div>
        <div className={styles.statusRow}>
          <span className={`${styles.connectionDot} ${styles[wrapperConnection.tone]}`} aria-hidden="true" />
          <span className={styles.statusText}>{wrapperConnection.label}</span>
          {isBusy ? <span className={styles.busyBadge}>planning</span> : null}
        </div>
      </div>
      {splitActivityCard}

      <ConversationSurface
        model={model}
        connectionState={connectionState}
        isLoading={isLoading}
        errorMessage={errorMessage}
        showHeader={false}
        emptyTitle="Planning conversation"
        emptyHint="Use a split action below to start a planning turn for this node."
      />

      <div className={styles.actions}>
        <button type="button" disabled={!canSplit} onClick={() => void handleSplit('walking_skeleton')}>
          Walking Skeleton
        </button>
        <button type="button" disabled={!canSplit} onClick={() => void handleSplit('slice')}>
          Slice
        </button>
      </div>
    </div>
  )
}
