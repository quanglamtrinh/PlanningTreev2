import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { RollupStatus } from '../../api/types'
import styles from './ReviewGraphNode.module.css'

export type ReviewGraphNodeData = {
  parentNodeId: string
  parentTitle: string
  parentHierarchicalNumber: string
  checkpointCount: number
  rollupStatus: RollupStatus | null
  pendingSiblingCount: number
}

const ROLLUP_LABELS: Record<RollupStatus, string> = {
  pending: 'Pending',
  ready: 'Ready',
  accepted: 'Accepted',
}

function ReviewGraphNodeComponent({ data }: NodeProps) {
  const d = data as ReviewGraphNodeData

  const rollupLabel = d.rollupStatus ? ROLLUP_LABELS[d.rollupStatus] : null
  const rollupClassName = d.rollupStatus
    ? `${styles.rollupBadge} ${styles[`rollup_${d.rollupStatus}`] ?? ''}`
    : ''

  return (
    <div className={styles.wrapper}>
      <Handle
        className={styles.handle}
        type="target"
        position={Position.Bottom}
        id="in"
        isConnectable={false}
      />
      <div
        className={`${styles.card} nodrag nopan`}
        data-testid={`graph-review-node-${d.parentNodeId}`}
        data-parent-node-id={d.parentNodeId}
      >
        <p className={styles.eyebrow}>Review</p>
        <h3 className={styles.title}>Review</h3>
        <p className={styles.subtitle}>
          for <span className={styles.parentNumber}>{d.parentHierarchicalNumber}</span>{' '}
          {d.parentTitle}
        </p>
        <div className={styles.stats}>
          {d.checkpointCount > 0 && (
            <span className={styles.stat}>
              {d.checkpointCount} checkpoint{d.checkpointCount !== 1 ? 's' : ''}
            </span>
          )}
          {d.pendingSiblingCount > 0 && (
            <span className={styles.stat}>
              {d.pendingSiblingCount} pending
            </span>
          )}
          {rollupLabel && (
            <span className={rollupClassName}>{rollupLabel}</span>
          )}
        </div>
      </div>
      <Handle
        className={styles.handle}
        type="source"
        position={Position.Top}
        id="out"
        isConnectable={false}
      />
    </div>
  )
}

export const ReviewGraphNode = memo(ReviewGraphNodeComponent) as typeof ReviewGraphNodeComponent
