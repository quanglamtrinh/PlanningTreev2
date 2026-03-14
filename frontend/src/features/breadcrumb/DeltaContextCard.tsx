import { useState } from 'react'

import type { DeltaContextPacket } from '../../api/types'
import { useAskStore } from '../../stores/ask-store'
import styles from './DeltaContextCard.module.css'

type Props = {
  packet: DeltaContextPacket
  projectId: string
  nodeId: string
  askActive: boolean
  planningActive: boolean
  nodeReadOnly: boolean
  nodeHasActiveChildren: boolean
}

function formatTimestamp(value: string | null) {
  if (!value) {
    return null
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function statusClass(status: DeltaContextPacket['status']) {
  switch (status) {
    case 'pending':
      return styles.statusPending
    case 'approved':
      return styles.statusApproved
    case 'merged':
      return styles.statusMerged
    case 'rejected':
      return styles.statusRejected
    case 'blocked':
      return styles.statusBlocked
  }
}

export function DeltaContextCard({
  packet,
  projectId,
  nodeId,
  askActive,
  planningActive,
  nodeReadOnly,
  nodeHasActiveChildren,
}: Props) {
  const approvePacket = useAskStore((state) => state.approvePacket)
  const rejectPacket = useAskStore((state) => state.rejectPacket)
  const mergePacket = useAskStore((state) => state.mergePacket)
  const [submittingAction, setSubmittingAction] = useState<'approve' | 'reject' | 'merge' | null>(null)

  const disableApprove = Boolean(submittingAction) || nodeReadOnly || planningActive || nodeHasActiveChildren
  const disableReject = Boolean(submittingAction) || nodeReadOnly || planningActive
  const disableMerge =
    Boolean(submittingAction) || nodeReadOnly || planningActive || nodeHasActiveChildren || askActive

  async function handleApprove() {
    setSubmittingAction('approve')
    try {
      await approvePacket(projectId, nodeId, packet.packet_id)
    } finally {
      setSubmittingAction(null)
    }
  }

  async function handleReject() {
    setSubmittingAction('reject')
    try {
      await rejectPacket(projectId, nodeId, packet.packet_id)
    } finally {
      setSubmittingAction(null)
    }
  }

  async function handleMerge() {
    setSubmittingAction('merge')
    try {
      await mergePacket(projectId, nodeId, packet.packet_id)
    } finally {
      setSubmittingAction(null)
    }
  }

  const mergedAt = formatTimestamp(packet.merged_at)

  return (
    <article className={styles.card}>
      <h4 className={styles.summary}>{packet.summary}</h4>
      <p className={styles.contextPreview}>{packet.context_text}</p>

      <div className={styles.meta}>
        <span className={`${styles.statusBadge} ${statusClass(packet.status)}`}>{packet.status}</span>
        <span className={styles.suggestedBy}>Suggested by {packet.suggested_by}</span>
      </div>

      {packet.status === 'merged' && mergedAt ? (
        <p className={styles.statusReason}>Merged {mergedAt}</p>
      ) : null}
      {(packet.status === 'rejected' || packet.status === 'blocked') && packet.status_reason ? (
        <p className={styles.statusReason}>{packet.status_reason}</p>
      ) : null}

      {packet.status === 'pending' ? (
        <div className={styles.actions}>
          <button
            type="button"
            className={`${styles.actionBtn} ${styles.actionBtnPrimary} ${
              disableApprove ? styles.actionBtnDisabled : ''
            }`}
            disabled={disableApprove}
            onClick={() => void handleApprove()}
          >
            Approve
          </button>
          <button
            type="button"
            className={`${styles.actionBtn} ${styles.actionBtnDanger} ${
              disableReject ? styles.actionBtnDisabled : ''
            }`}
            disabled={disableReject}
            onClick={() => void handleReject()}
          >
            Reject
          </button>
        </div>
      ) : null}

      {packet.status === 'approved' ? (
        <div className={styles.actions}>
          <button
            type="button"
            className={`${styles.actionBtn} ${styles.actionBtnPrimary} ${
              disableMerge ? styles.actionBtnDisabled : ''
            }`}
            disabled={disableMerge}
            onClick={() => void handleMerge()}
          >
            Merge
          </button>
          <button
            type="button"
            className={`${styles.actionBtn} ${styles.actionBtnDanger} ${
              disableReject ? styles.actionBtnDisabled : ''
            }`}
            disabled={disableReject}
            onClick={() => void handleReject()}
          >
            Reject
          </button>
        </div>
      ) : null}
    </article>
  )
}
