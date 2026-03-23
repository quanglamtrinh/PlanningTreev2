import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import styles from './ReviewGraphNode.module.css'

export type ReviewGraphNodeData = {
  parentNodeId: string
  parentTitle: string
  parentHierarchicalNumber: string
}

function ReviewGraphNodeComponent({ data }: NodeProps) {
  const d = data as ReviewGraphNodeData

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
