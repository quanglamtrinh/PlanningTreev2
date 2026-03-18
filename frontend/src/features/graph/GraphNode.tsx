import { memo, useEffect, useRef, useState } from 'react'
import { Handle, Position, type NodeProps } from '@xyflow/react'
import type { SplitMode } from '../../api/types'
import { NodeStatusBadge } from '../node/NodeStatusBadge'
import { GRAPH_SPLIT_OPTIONS } from './splitModes'
import styles from './GraphNode.module.css'

const CONTROL_CLASS_NAME = 'nodrag nopan'

export type GraphNodeData = {
  node: {
    node_id: string
    title: string
    description: string
    status: 'locked' | 'draft' | 'ready' | 'in_progress' | 'done'
    depth: number
    child_ids: string[]
    is_superseded: boolean
    hierarchical_number: string
  }
  isCurrent: boolean
  isSelected: boolean
  isCollapsed: boolean
  directHiddenChildrenCount: number
  canCreateChild: boolean
  canFinishTask: boolean
  canSplit: boolean
  isSplitting: boolean
  isSplitDisabled: boolean
  onSelect: (nodeId: string) => void
  onToggleCollapse: (nodeId: string) => void
  onCreateChild: (nodeId: string) => void
  onSplit: (nodeId: string, mode: SplitMode) => void
  onOpenBreadcrumb: (nodeId: string) => void
  onFinishTask: (nodeId: string) => void
  onInfoClick: (nodeId: string) => void
}

function GraphNodeComponent({ data }: NodeProps) {
  const nodeData = data as GraphNodeData
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const descriptionPreview =
    nodeData.node.description.trim().length > 0
      ? nodeData.node.description.trim()
      : 'No description yet.'

  useEffect(() => {
    if (!menuOpen) {
      return undefined
    }

    function handlePointerDown(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as globalThis.Node)) {
        setMenuOpen(false)
      }
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpen(false)
      }
    }

    document.addEventListener('mousedown', handlePointerDown, true)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown, true)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [menuOpen])

  return (
    <div className={styles.wrapper}>
      <Handle className={styles.handle} type="target" position={Position.Left} isConnectable={false} />
      <div
        role="button"
        tabIndex={0}
        className={`${styles.card} ${CONTROL_CLASS_NAME} ${nodeData.isSelected ? styles.selected : ''} ${nodeData.isCurrent ? styles.current : ''} ${nodeData.node.status === 'locked' ? styles.locked : ''} ${nodeData.isSplitting ? styles.splitting : ''}`}
        data-testid={`graph-node-${nodeData.node.node_id}`}
        data-node-id={nodeData.node.node_id}
        data-node-title={nodeData.node.title}
        data-status={nodeData.node.status}
        onClick={() => nodeData.onSelect(nodeData.node.node_id)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            nodeData.onSelect(nodeData.node.node_id)
          }
        }}
      >
        <div className={styles.header}>
          <div className={styles.titleWrap}>
            <p className={styles.title}>
              <span className={styles.number}>{nodeData.node.hierarchical_number}</span>
              <span className={styles.separator}>/</span>
              <span>{nodeData.node.title}</span>
            </p>
            <NodeStatusBadge status={nodeData.node.status} />
          </div>
          <div className={styles.headerControls}>
            {nodeData.node.child_ids.length > 0 ? (
              <button
                type="button"
                className={`${styles.collapseToggle} ${CONTROL_CLASS_NAME}`}
                onClick={(event) => {
                  event.stopPropagation()
                  nodeData.onToggleCollapse(nodeData.node.node_id)
                }}
                aria-label={nodeData.isCollapsed ? 'Expand node' : 'Collapse node'}
                title={nodeData.isCollapsed ? 'Expand node' : 'Collapse node'}
              >
                {nodeData.isCollapsed ? '+' : '−'}
                {nodeData.isCollapsed && nodeData.directHiddenChildrenCount > 0 ? (
                  <span className={styles.hiddenCount}>{nodeData.directHiddenChildrenCount}</span>
                ) : null}
              </button>
            ) : null}
            <button
              type="button"
              className={`${styles.infoBtn} ${CONTROL_CLASS_NAME}`}
              onClick={(event) => {
                event.stopPropagation()
                nodeData.onInfoClick(nodeData.node.node_id)
              }}
              aria-label="Node details"
              title="View node details"
            >
              ℹ
            </button>
          </div>
        </div>

        <p className={styles.description}>{descriptionPreview}</p>
        <p className={styles.meta}>
          Depth {nodeData.node.depth} / {nodeData.node.child_ids.length} child
          {nodeData.node.child_ids.length === 1 ? '' : 'ren'}
        </p>
        {nodeData.isSplitting ? <p className={styles.activity}>AI planning in progress...</p> : null}
      </div>

      <div className={`${styles.menuAnchor} ${CONTROL_CLASS_NAME}`} ref={menuRef}>
        <button
          type="button"
          className={`${styles.badge} ${CONTROL_CLASS_NAME} ${menuOpen ? styles.badgeOpen : ''}`}
          onClick={(event) => {
            event.stopPropagation()
            setMenuOpen((value) => !value)
          }}
          aria-label="Node actions"
          title="Node actions"
        >
          <svg viewBox="0 0 20 20" className={styles.badgeIcon} aria-hidden="true">
            <path d="M11 2 4 11h5l-1 7 8-10h-5z" fill="currentColor" />
          </svg>
        </button>

        {menuOpen ? (
          <div className={`${styles.dropdown} ${CONTROL_CLASS_NAME}`}>
            <div className={styles.dropdownSection}>
              <p className={styles.dropdownLabel}>Execution</p>
              <button
                type="button"
                className={`${styles.menuItem} ${CONTROL_CLASS_NAME}`}
                disabled={!nodeData.canCreateChild}
                onClick={() => {
                  setMenuOpen(false)
                  nodeData.onCreateChild(nodeData.node.node_id)
                }}
              >
                <span className={styles.menuTitle}>Create Child</span>
                <span className={styles.menuDesc}>Append a new child node under this card.</span>
              </button>
              <button
                type="button"
                className={`${styles.menuItem} ${CONTROL_CLASS_NAME}`}
                onClick={() => {
                  setMenuOpen(false)
                  nodeData.onOpenBreadcrumb(nodeData.node.node_id)
                }}
              >
                <span className={styles.menuTitle}>Open Breadcrumb</span>
                <span className={styles.menuDesc}>Open breadcrumb without seeding the execution draft.</span>
              </button>
              <button
                type="button"
                className={`${styles.menuItem} ${CONTROL_CLASS_NAME}`}
                disabled={!nodeData.canFinishTask}
                onClick={() => {
                  setMenuOpen(false)
                  nodeData.onFinishTask(nodeData.node.node_id)
                }}
              >
                <span className={styles.menuTitle}>Finish Task</span>
                <span className={styles.menuDesc}>Open the breadcrumb workflow and continue this leaf node.</span>
              </button>
            </div>

            <div className={styles.dropdownSection}>
              <p className={styles.dropdownLabel}>AI Planning</p>
              {GRAPH_SPLIT_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  className={`${styles.menuItem} ${CONTROL_CLASS_NAME}`}
                  disabled={!nodeData.canSplit || nodeData.isSplitDisabled}
                  onClick={() => {
                    setMenuOpen(false)
                    nodeData.onSplit(nodeData.node.node_id, option.id)
                  }}
                >
                  <span className={styles.menuTitle}>
                    {nodeData.isSplitting ? 'Splitting...' : option.label}
                  </span>
                  <span className={styles.menuDesc}>{option.description}</span>
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <Handle className={styles.handle} type="source" position={Position.Right} isConnectable={false} />
    </div>
  )
}

export const GraphNode = memo(GraphNodeComponent)
