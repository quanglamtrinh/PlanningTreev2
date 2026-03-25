import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { formatReviewChainLabel } from '../../utils/reviewSiblingLabels'
import styles from './GhostGraphNode.module.css'

export type GhostGraphNodeData = {
  parentId: string
  title: string
  siblingIndex: number
  parentHierarchicalNumber: string
}

function GhostGraphNodeComponent({ data }: NodeProps) {
  const d = data as GhostGraphNodeData
  const siblingLabel = formatReviewChainLabel(d.parentHierarchicalNumber, d.siblingIndex)
  const waitingLabel =
    d.siblingIndex > 1
      ? `Waiting for ${formatReviewChainLabel(d.parentHierarchicalNumber, d.siblingIndex - 1)} review`
      : 'Pending'

  return (
    <div className={styles.wrapper}>
      <Handle
        className={styles.handle}
        type="target"
        position={Position.Top}
        id="in"
        isConnectable={false}
      />
      <div
        className={`${styles.card} nodrag nopan`}
        data-testid={`graph-ghost-node-${d.siblingIndex}`}
      >
        <p className={styles.number}>{siblingLabel}</p>
        <p className={styles.title}>{d.title}</p>
        <p className={styles.waiting}>{waitingLabel}</p>
      </div>
    </div>
  )
}

export const GhostGraphNode = memo(GhostGraphNodeComponent) as typeof GhostGraphNodeComponent
