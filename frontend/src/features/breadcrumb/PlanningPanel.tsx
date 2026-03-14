import { useMemo } from 'react'

import type { AgentActivity, NodeDocuments, NodeRecord, PlanningTurn } from '../../api/types'
import { useProjectStore } from '../../stores/project-store'
import { AgentActivityCard } from './AgentActivityCard'
import styles from './PlanningPanel.module.css'

type Props = {
  node: NodeRecord
  documents?: NodeDocuments
  activity?: AgentActivity
}

function renderMetaLine(label: string, value: string | undefined) {
  if (!value) {
    return null
  }

  return (
    <p className={styles.metaLine}>
      <span className={styles.metaLabel}>{label}</span> {value}
    </p>
  )
}

function renderSplitPayload(payload: Record<string, unknown> | undefined) {
  if (!payload) {
    return null
  }
  const epics = Array.isArray(payload.epics) ? payload.epics : null
  const subtasks = Array.isArray(payload.subtasks) ? payload.subtasks : null

  if (epics) {
    return (
      <div className={styles.renderGrid}>
        {epics.map((epic, index) => {
          if (!epic || typeof epic !== 'object') {
            return null
          }
          const typedEpic = epic as {
            title?: string
            prompt?: string
            phases?: Array<{ prompt?: string; definition_of_done?: string }>
          }
          return (
            <article key={`${typedEpic.title ?? 'epic'}-${index}`} className={styles.renderCard}>
              <div className={styles.subgroup}>
                <h4 className={styles.renderHeading}>{typedEpic.title ?? `Epic ${index + 1}`}</h4>
                {typedEpic.prompt ? <p className={styles.renderSupporting}>{typedEpic.prompt}</p> : null}
              </div>
              <div className={styles.phaseList}>
                {(typedEpic.phases ?? []).map((phase, phaseIndex) => (
                  <div key={`${typedEpic.title ?? 'phase'}-${phaseIndex}`} className={styles.phaseItem}>
                    <strong className={styles.itemTitle}>{phase.prompt ?? `Phase ${phaseIndex + 1}`}</strong>
                    {phase.definition_of_done ? (
                      <span className={styles.itemDesc}>{phase.definition_of_done}</span>
                    ) : null}
                  </div>
                ))}
              </div>
            </article>
          )
        })}
      </div>
    )
  }

  if (subtasks) {
    return (
      <div className={styles.renderGrid}>
        {subtasks.map((subtask, index) => {
          if (!subtask || typeof subtask !== 'object') {
            return null
          }
          const typedSubtask = subtask as {
            order?: number
            prompt?: string
            risk_reason?: string
            what_unblocks?: string
          }
          return (
            <article
              key={`${typedSubtask.order ?? index}-${typedSubtask.prompt ?? 'subtask'}`}
              className={styles.renderCard}
            >
              <div className={styles.subgroup}>
                <h4 className={styles.renderHeading}>Slice {typedSubtask.order ?? index + 1}</h4>
                {typedSubtask.prompt ? <p className={styles.itemTitle}>{typedSubtask.prompt}</p> : null}
                {renderMetaLine('Risk:', typedSubtask.risk_reason)}
                {renderMetaLine('Unblocks:', typedSubtask.what_unblocks)}
              </div>
            </article>
          )
        })}
      </div>
    )
  }

  return null
}

function turnKey(turn: PlanningTurn, index: number) {
  return `${turn.turn_id}:${turn.role}:${index}`
}

function turnLabel(turn: PlanningTurn) {
  if (turn.role === 'assistant') {
    return 'Assistant'
  }
  if (turn.role === 'tool_call') {
    return 'Rendered Split'
  }
  if (turn.role === 'context_merge') {
    return 'Context Merge'
  }
  return 'You'
}

function turnClassName(turn: PlanningTurn) {
  if (turn.role === 'assistant' || turn.role === 'context_merge') {
    return styles.assistantTurn
  }
  if (turn.role === 'tool_call') {
    return styles.toolTurn
  }
  return styles.userTurn
}

export function PlanningPanel({ node, documents, activity }: Props) {
  const snapshot = useProjectStore((state) => state.snapshot)
  const planningHistoryByNode = useProjectStore((state) => state.planningHistoryByNode)
  const planningConnectionStatus = useProjectStore((state) => state.planningConnectionStatus)
  const isSplittingNode = useProjectStore((state) => state.isSplittingNode)
  const splittingNodeId = useProjectStore((state) => state.splittingNodeId)
  const splitNode = useProjectStore((state) => state.splitNode)

  const turns = planningHistoryByNode[node.node_id] ?? []
  const isBusy = isSplittingNode && splittingNodeId === node.node_id
  const nodeLabels = useMemo(() => {
    const labels = new Map<string, string>()
    if (!snapshot) {
      return labels
    }
    snapshot.tree_state.node_registry.forEach((item) => {
      labels.set(item.node_id, `${item.hierarchical_number} ${item.title}`)
    })
    return labels
  }, [snapshot])
  const activeChildren = useMemo(() => {
    if (!snapshot) {
      return []
    }
    return node.child_ids
      .map((childId) => snapshot.tree_state.node_registry.find((item) => item.node_id === childId) ?? null)
      .filter((child) => Boolean(child && !child.is_superseded))
  }, [node.child_ids, snapshot])

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

  const canSplit = !isBusy && !node.is_superseded && node.status !== 'done'
  const splitFailure = documents?.state.last_agent_failure?.operation === 'split'
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
          <span className={`${styles.connectionDot} ${styles[planningConnectionStatus]}`} aria-hidden="true" />
          <span className={styles.statusText}>{planningConnectionStatus}</span>
          {isBusy ? <span className={styles.busyBadge}>planning</span> : null}
        </div>
      </div>
      {splitActivityCard}

      <div className={styles.thread}>
        {turns.length === 0 ? (
          <div className={styles.emptyState}>
            Use a split action below to start a planning turn for this node.
          </div>
        ) : null}
        {turns.map((turn, index) => (
          <article
            key={turnKey(turn, index)}
            className={`${styles.turn} ${turnClassName(turn)}`}
          >
            <div className={styles.turnMetaRow}>
              <div className={styles.turnMeta}>{turnLabel(turn)}</div>
              {turn.is_inherited ? (
                <span className={styles.inheritedBadge}>
                  Inherited from {nodeLabels.get(turn.origin_node_id) ?? turn.origin_node_id}
                </span>
              ) : null}
            </div>
            {turn.role === 'tool_call' ? (
              renderSplitPayload(turn.arguments?.payload)
            ) : turn.role === 'context_merge' ? (
              <div className={styles.turnBody}>
                {turn.summary ? <strong>{turn.summary}</strong> : null}
                {turn.summary && turn.content ? '\n\n' : ''}
                {turn.content || ''}
              </div>
            ) : (
              <div className={styles.turnBody}>{turn.content || ''}</div>
            )}
          </article>
        ))}
      </div>

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
