import { memo } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import { formatReviewChainLabel } from '../../utils/reviewSiblingLabels'
import { NodeStatusBadge } from '../node/NodeStatusBadge'
import graphStyles from './GraphNode.module.css'
import ghostStyles from './GhostGraphNode.module.css'

const CONTROL_CLASS_NAME = 'nodrag nopan'

export type GhostGraphNodeData = {
  parentId: string
  title: string
  siblingIndex: number
  parentHierarchicalNumber: string
  objective: string
}

function GhostGraphNodeComponent({ data }: NodeProps) {
  const d = data as GhostGraphNodeData
  const siblingLabel = formatReviewChainLabel(d.parentHierarchicalNumber, d.siblingIndex)
  const waitingLabel =
    d.siblingIndex > 1
      ? `Waiting for ${formatReviewChainLabel(d.parentHierarchicalNumber, d.siblingIndex - 1)} review`
      : 'Pending'
  const objectiveTrimmed = d.objective.trim()
  const descriptionText = objectiveTrimmed || waitingLabel

  return (
    <div className={`${graphStyles.wrapper} ${ghostStyles.ghostMuted}`}>
      <Handle
        className={graphStyles.handle}
        type="target"
        position={Position.Top}
        id="in"
        isConnectable={false}
      />
      <Handle
        className={graphStyles.handle}
        type="source"
        position={Position.Top}
        id="to-review"
        isConnectable={false}
        style={{ left: '50%' }}
      />
      <div
        className={`${graphStyles.card} ${ghostStyles.ghostCard} nodrag nopan`}
        data-testid={`graph-ghost-node-${d.siblingIndex}`}
      >
        <aside className={graphStyles.nodeRail} aria-label="Node controls (preview)">
          <span className={graphStyles.railLayerIndex} aria-hidden="true">
            {siblingLabel}
          </span>
          <span
            className={`${graphStyles.infoBtn} ${ghostStyles.nonInteractive} ${CONTROL_CLASS_NAME}`}
            aria-hidden="true"
          >
            i
          </span>
          <div className={graphStyles.railMidSpacer} aria-hidden="true" />
          <span
            className={`${graphStyles.descToggle} ${ghostStyles.nonInteractive} ${CONTROL_CLASS_NAME}`}
            aria-hidden="true"
          >
            <svg viewBox="0 0 20 20" className={graphStyles.descToggleIcon} aria-hidden="true">
              <path
                fill="currentColor"
                d="M5.23 12.77a.75.75 0 0 1 0-1.06L9.47 7.47a.75.75 0 0 1 1.06 0l4.24 4.24a.75.75 0 1 1-1.06 1.06L10 9.06l-3.71 3.71a.75.75 0 0 1-1.06 0Z"
              />
            </svg>
          </span>
        </aside>
        <div className={graphStyles.nodeMain}>
          <div className={graphStyles.header}>
            <div className={graphStyles.titleRow}>
              <p className={graphStyles.title}>{d.title}</p>
              <div className={graphStyles.titleRowActions}>
                <NodeStatusBadge
                  status="draft"
                  className={graphStyles.graphStatusBadge}
                />
              </div>
            </div>
            <p className={graphStyles.description}>{descriptionText}</p>
          </div>
        </div>
      </div>

      <div className={`${graphStyles.menuAnchor} ${CONTROL_CLASS_NAME}`}>
        <span
          className={`${graphStyles.badge} ${ghostStyles.nonInteractive}`}
          aria-hidden="true"
        >
          <svg viewBox="0 0 20 20" className={graphStyles.badgeIcon} aria-hidden="true">
            <path d="M11 2 4 11h5l-1 7 8-10h-5z" fill="currentColor" />
          </svg>
        </span>
      </div>
    </div>
  )
}

export const GhostGraphNode = memo(GhostGraphNodeComponent) as typeof GhostGraphNodeComponent
