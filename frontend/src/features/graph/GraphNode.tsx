import { memo, useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'
import { createPortal } from 'react-dom'
import { Handle, Position, useStore, type NodeProps } from '@xyflow/react'
import { NodeStatusBadge } from '../node/NodeStatusBadge'
import { useGraphNodeActions } from './graphNodeActionsContext'
import { GRAPH_SPLIT_OPTIONS } from './splitModes'
import styles from './GraphNode.module.css'

const CONTROL_CLASS_NAME = 'nodrag nopan'

const DROPDOWN_GAP = 8
const VIEW_MARGIN = 8

function placeDropdownNearAnchor(anchorEl: HTMLElement, dropdownEl: HTMLElement) {
  const el = dropdownEl
  el.style.maxHeight = ''
  el.style.overflowY = ''

  const anchor = anchorEl.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const G = DROPDOWN_GAP
  const M = VIEW_MARGIN

  const menuWidth = Math.max(el.offsetWidth || el.getBoundingClientRect().width, 220)
  const menuHeight =
    el.offsetHeight || el.scrollHeight || el.getBoundingClientRect().height || 1

  let left = anchor.right + G
  if (left + menuWidth > vw - M) {
    const leftOfAnchor = anchor.left - G - menuWidth
    if (leftOfAnchor >= M) {
      left = leftOfAnchor
    } else {
      left = Math.max(M, vw - menuWidth - M)
    }
  }

  const spaceBelow = vh - M - anchor.bottom - G
  const spaceAbove = anchor.top - M - G

  let top: number
  let maxHeightPx: number | undefined

  if (menuHeight <= spaceBelow) {
    top = anchor.bottom + G
  } else if (menuHeight <= spaceAbove) {
    top = anchor.top - G - menuHeight
  } else if (spaceBelow >= spaceAbove) {
    top = anchor.bottom + G
    maxHeightPx = Math.max(120, spaceBelow)
  } else {
    top = M
    maxHeightPx = Math.max(120, spaceAbove)
  }

  const blockH = maxHeightPx ?? menuHeight
  if (top + blockH > vh - M) {
    top = Math.max(M, vh - M - blockH)
  }
  if (top < M) {
    top = M
    maxHeightPx = Math.max(120, vh - M - top)
  }

  el.style.position = 'fixed'
  el.style.left = `${left}px`
  el.style.top = `${top}px`
  el.style.right = 'auto'
  el.style.bottom = 'auto'
  el.style.zIndex = '10050'
  if (maxHeightPx !== undefined) {
    el.style.maxHeight = `${maxHeightPx}px`
    el.style.overflowY = 'auto'
  }
}

function GraphNodeActionsDropdown({
  anchorRef,
  nodeId,
  canCreateChild,
  canFinishTask,
  canSplit,
  canOpenBreadcrumb,
  isSplitting,
  isSplitDisabled,
  onClose,
}: {
  anchorRef: RefObject<HTMLDivElement | null>
  nodeId: string
  canCreateChild: boolean
  canFinishTask: boolean
  canSplit: boolean
  canOpenBreadcrumb: boolean
  isSplitting: boolean
  isSplitDisabled: boolean
  onClose: () => void
}) {
  const actions = useGraphNodeActions()
  const dropdownRef = useRef<HTMLDivElement | null>(null)
  const transform = useStore((s) => s.transform)

  useEffect(() => {
    function handlePointerDown(event: MouseEvent) {
      const target = event.target as globalThis.Node
      if (anchorRef.current?.contains(target) || dropdownRef.current?.contains(target)) {
        return
      }
      onClose()
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
      }
    }

    document.addEventListener('mousedown', handlePointerDown, true)
    document.addEventListener('keydown', handleEscape)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown, true)
      document.removeEventListener('keydown', handleEscape)
    }
  }, [anchorRef, onClose])

  useLayoutEffect(() => {
    const anchor = anchorRef.current
    const dropdown = dropdownRef.current
    if (!anchor || !dropdown) {
      return undefined
    }

    const apply = () => {
      placeDropdownNearAnchor(anchor, dropdown)
    }

    apply()
    window.addEventListener('resize', apply)
    return () => window.removeEventListener('resize', apply)
  }, [anchorRef, transform])

  return createPortal(
    <div ref={dropdownRef} className={`${styles.dropdown} ${CONTROL_CLASS_NAME}`}>
      <div className={styles.dropdownSection}>
        <p className={styles.dropdownLabel}>Actions</p>
        <button
          type="button"
          className={`${styles.menuItem} ${CONTROL_CLASS_NAME}`}
          disabled={!canCreateChild}
          onClick={() => {
            onClose()
            actions.createChild(nodeId)
          }}
        >
          <span className={styles.menuTitle}>Create Child</span>
          <span className={styles.menuDesc}>Append a new child node under this card.</span>
        </button>
        <button
          type="button"
          className={`${styles.menuItem} ${CONTROL_CLASS_NAME}`}
          disabled={!canOpenBreadcrumb}
          onClick={() => {
            onClose()
            actions.openBreadcrumb(nodeId)
          }}
        >
          <span className={styles.menuTitle}>Open Breadcrumb</span>
          <span className={styles.menuDesc}>
            {canOpenBreadcrumb
              ? 'Open the placeholder breadcrumb route for this node.'
              : 'Codex CLI is not installed.'}
          </span>
        </button>
        <button
          type="button"
          className={`${styles.menuItem} ${CONTROL_CLASS_NAME}`}
          onClick={() => {
            onClose()
            if (actions.graphViewRootId === nodeId) {
              actions.setGraphViewRoot(null)
            } else {
              actions.setGraphViewRoot(nodeId)
            }
          }}
        >
          <span className={styles.menuTitle}>
            {actions.graphViewRootId === nodeId ? 'Unset current root' : 'Set as current root'}
          </span>
          <span className={styles.menuDesc}>
            {actions.graphViewRootId === nodeId
              ? 'Show the full project tree again.'
              : 'Show only this node and its descendants in the graph.'}
          </span>
        </button>
        <button
          type="button"
          className={`${styles.menuItem} ${CONTROL_CLASS_NAME}`}
          disabled={!canFinishTask}
          onClick={() => {
            onClose()
            actions.finishTask(nodeId)
          }}
        >
          <span className={styles.menuTitle}>Finish Task</span>
          <span className={styles.menuDesc}>Jump to the breadcrumb placeholder for this leaf node.</span>
        </button>
      </div>

      <div className={styles.dropdownSection}>
        <p className={styles.dropdownLabel}>AI Split</p>
        {GRAPH_SPLIT_OPTIONS.map((option) => (
          <button
            key={option.id}
            type="button"
            className={`${styles.menuItem} ${CONTROL_CLASS_NAME}`}
            disabled={!canSplit || isSplitDisabled}
            onClick={() => {
              onClose()
              actions.split(nodeId, option.id)
            }}
          >
            <span className={styles.menuTitle}>
              {isSplitting ? 'Splitting...' : option.label}
            </span>
            <span className={styles.menuDesc}>{option.description}</span>
          </button>
        ))}
      </div>
    </div>,
    document.body,
  )
}

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
  canOpenBreadcrumb: boolean
  isSplitting: boolean
  isSplitDisabled: boolean
  graphViewRootId: string | null
}

function childIdsEqual(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  return a.every((id, i) => id === b[i])
}

function graphNodePropsAreEqual(prev: NodeProps, next: NodeProps): boolean {
  if (prev.id !== next.id) return false
  if (prev.selected !== next.selected) return false
  if (prev.dragging !== next.dragging) return false
  const a = prev.data as GraphNodeData
  const b = next.data as GraphNodeData
  if (a === b) return true
  return (
    a.isCurrent === b.isCurrent &&
    a.isSelected === b.isSelected &&
    a.isCollapsed === b.isCollapsed &&
    a.directHiddenChildrenCount === b.directHiddenChildrenCount &&
    a.canCreateChild === b.canCreateChild &&
    a.canFinishTask === b.canFinishTask &&
    a.canSplit === b.canSplit &&
    a.canOpenBreadcrumb === b.canOpenBreadcrumb &&
    a.isSplitting === b.isSplitting &&
    a.isSplitDisabled === b.isSplitDisabled &&
    a.node.node_id === b.node.node_id &&
    a.node.title === b.node.title &&
    a.node.description === b.node.description &&
    a.node.status === b.node.status &&
    a.node.depth === b.node.depth &&
    a.node.is_superseded === b.node.is_superseded &&
    a.node.hierarchical_number === b.node.hierarchical_number &&
    childIdsEqual(a.node.child_ids, b.node.child_ids)
  )
}

function GraphNodeComponent({ data }: NodeProps) {
  const actions = useGraphNodeActions()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const closeMenu = useCallback(() => setMenuOpen(false), [])
  const d = data as GraphNodeData

  return (
    <div className={styles.wrapper}>
      <Handle className={styles.handle} type="target" position={Position.Top} isConnectable={false} />
      <div
        role="button"
        tabIndex={0}
        className={`${styles.card} ${CONTROL_CLASS_NAME} ${d.isSelected ? styles.selected : ''} ${d.isCurrent ? styles.current : ''} ${d.node.status === 'locked' ? styles.locked : ''} ${d.isSplitting ? styles.splitting : ''}`}
        data-testid={`graph-node-${d.node.node_id}`}
        data-node-id={d.node.node_id}
        data-node-title={d.node.title}
        data-status={d.node.status}
        onClick={() => actions.selectNode(d.node.node_id)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault()
            actions.selectNode(d.node.node_id)
          }
        }}
      >
        <div className={styles.header}>
          <div className={styles.titleWrap}>
            <p className={styles.title}>
              <span className={styles.number}>{d.node.hierarchical_number}</span>
              <span className={styles.separator}>/</span>
              <span>{d.node.title}</span>
            </p>
            <div className={styles.badgeRow}>
              {d.node.status === 'locked' ? (
                <span className={styles.lockIcon} title="Locked" aria-hidden="true">
                  <svg viewBox="0 0 20 20" fill="currentColor">
                    <path
                      fillRule="evenodd"
                      d="M5 9V7a5 5 0 0110 0v2h1a1 1 0 011 1v7a2 2 0 01-2 2H6a2 2 0 01-2-2v-7a1 1 0 011-1h1zm2-2a3 3 0 016 0v2H7V7z"
                      clipRule="evenodd"
                    />
                  </svg>
                </span>
              ) : null}
              <NodeStatusBadge status={d.node.status} />
            </div>
          </div>
          <div className={styles.headerControls}>
            {d.node.child_ids.length > 0 ? (
              <button
                type="button"
                className={`${styles.collapseToggle} ${CONTROL_CLASS_NAME}`}
                onClick={(event) => {
                  event.stopPropagation()
                  actions.toggleCollapse(d.node.node_id)
                }}
                aria-label={d.isCollapsed ? 'Expand node' : 'Collapse node'}
                title={d.isCollapsed ? 'Expand node' : 'Collapse node'}
              >
                {d.isCollapsed ? '+' : '-'}
                {d.isCollapsed && d.directHiddenChildrenCount > 0 ? (
                  <span className={styles.hiddenCount}>{d.directHiddenChildrenCount}</span>
                ) : null}
              </button>
            ) : null}
            <button
              type="button"
              className={`${styles.infoBtn} ${CONTROL_CLASS_NAME}`}
              onClick={(event) => {
                event.stopPropagation()
                actions.infoClick(d.node.node_id)
              }}
              aria-label="Node details"
              title="View node details"
            >
              i
            </button>
          </div>
        </div>

        {d.isSplitting ? <p className={styles.activity}>AI split in progress...</p> : null}
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
          <GraphNodeActionsDropdown
            anchorRef={menuRef}
            nodeId={d.node.node_id}
            canCreateChild={d.canCreateChild}
            canFinishTask={d.canFinishTask}
            canSplit={d.canSplit}
            canOpenBreadcrumb={d.canOpenBreadcrumb}
            isSplitting={d.isSplitting}
            isSplitDisabled={d.isSplitDisabled}
            onClose={closeMenu}
          />
        ) : null}
      </div>

      <Handle className={styles.handle} type="source" position={Position.Bottom} isConnectable={false} />
    </div>
  )
}

export const GraphNode = memo(GraphNodeComponent, graphNodePropsAreEqual) as typeof GraphNodeComponent
