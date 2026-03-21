import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Background,
  Controls,
  MarkerType,
  Panel,
  ReactFlow,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { NodeRecord, Snapshot, SplitJobStatus, SplitMode } from '../../api/types'
import { NodeDetailCard } from '../node/NodeDetailCard'
import {
  GraphNodeActionsProvider,
  type GraphNodeActions,
} from './graphNodeActionsContext'
import { GraphNode, type GraphNodeData } from './GraphNode'
import { buildTreeLayoutPositions } from './treeGraphLayout'
import styles from './TreeGraph.module.css'

const nodeTypes = {
  graphNode: GraphNode,
}

/** React Flow `.react-flow__panel` margin in TreeGraph.module.css */
const REACT_FLOW_PANEL_MARGIN_PX = 12

/** Expanded sidebar width — keep in sync with `.sidebar` in Sidebar.module.css */
const GRAPH_SIDEBAR_EXPANDED_PX = 270

/**
 * Fallback estimate for detail panel width (px) from CSS rules in TreeGraph.module.css.
 * Caps by the graph column width (window minus sidebar) so fitView matches the real pane.
 */
function graphDetailPanelWidthEstimatePx(innerWidth: number, isFullscreen: boolean): number {
  if (typeof window === 'undefined') {
    return 400
  }
  const graphColumnW = isFullscreen
    ? innerWidth
    : Math.max(200, innerWidth - GRAPH_SIDEBAR_EXPANDED_PX)
  const vw = innerWidth
  const raw =
    vw <= 920
      ? Math.min(Math.max(360, vw * 0.88), 520, vw - 32)
      : Math.min(Math.max(400, vw * 0.44), 720, vw - 40)
  return Math.min(raw, graphColumnW)
}

function graphDetailPanelRightReservePx(
  innerWidth: number,
  isFullscreen: boolean,
  measuredPanelWidthPx?: number,
  flowPaneWidthPx?: number,
): number {
  const fromDom =
    typeof measuredPanelWidthPx === 'number' && measuredPanelWidthPx > 40
      ? measuredPanelWidthPx + REACT_FLOW_PANEL_MARGIN_PX
      : graphDetailPanelWidthEstimatePx(innerWidth, isFullscreen) + REACT_FLOW_PANEL_MARGIN_PX
  if (typeof flowPaneWidthPx === 'number' && flowPaneWidthPx > 160) {
    return Math.min(Math.ceil(fromDom), Math.max(flowPaneWidthPx - 100, 80))
  }
  return Math.ceil(fromDom)
}

type Props = {
  snapshot: Snapshot
  selectedNodeId: string | null
  splitStatus: SplitJobStatus
  splittingNodeId: string | null
  isCreatingNode: boolean
  isResettingProject: boolean
  isResetDisabled: boolean
  codexAvailable: boolean
  onSelectNode: (nodeId: string, persist?: boolean) => Promise<void>
  onCreateChild: (parentId: string) => Promise<void>
  onSplitNode: (nodeId: string, mode: SplitMode) => Promise<void>
  onOpenBreadcrumb: (nodeId: string) => Promise<void>
  onFinishTask: (nodeId: string) => Promise<void>
  onResetProject: () => Promise<void>
}

function defaultCollapsedForStatus(status: NodeRecord['status']): boolean {
  return status === 'locked' || status === 'done'
}

function findVisibleSelectionFallback(
  selectedNodeId: string | null,
  visibleNodeIds: Set<string>,
  parentById: Map<string, string | null>,
  rootNodeId: string,
): string {
  if (!selectedNodeId || visibleNodeIds.has(selectedNodeId)) {
    return selectedNodeId ?? rootNodeId
  }

  let currentId: string | null = selectedNodeId
  const visited = new Set<string>()
  while (currentId && !visited.has(currentId)) {
    visited.add(currentId)
    const parentId: string | null = parentById.get(currentId) ?? null
    if (!parentId) {
      break
    }
    if (visibleNodeIds.has(parentId)) {
      return parentId
    }
    currentId = parentId
  }

  return rootNodeId
}

export function TreeGraph({
  snapshot,
  selectedNodeId,
  splitStatus,
  splittingNodeId,
  isCreatingNode: _isCreatingNode,
  isResettingProject,
  isResetDisabled,
  codexAvailable,
  onSelectNode,
  onCreateChild,
  onSplitNode,
  onOpenBreadcrumb,
  onFinishTask,
  onResetProject,
}: Props) {
  const [collapseOverrides, setCollapseOverrides] = useState<Record<string, boolean>>({})
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null)
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null)
  const graphShellRef = useRef<HTMLDivElement | null>(null)
  const handlerRef = useRef({
    onSelectNode,
    onCreateChild,
    onSplitNode,
    onOpenBreadcrumb,
    onFinishTask,
  })
  handlerRef.current = {
    onSelectNode,
    onCreateChild,
    onSplitNode,
    onOpenBreadcrumb,
    onFinishTask,
  }

  const nodeById = useMemo(
    () => new Map(snapshot.tree_state.node_registry.map((node) => [node.node_id, node])),
    [snapshot.tree_state.node_registry],
  )

  const graphNodeActions = useMemo<GraphNodeActions>(
    () => ({
      selectNode: (nodeId) => {
        void handlerRef.current.onSelectNode(nodeId, true)
      },
      toggleCollapse: (nodeId) => {
        setCollapseOverrides((current) => {
          const nodeRecord = nodeById.get(nodeId)
          if (!nodeRecord) {
            return current
          }
          const currentValue =
            typeof current[nodeId] === 'boolean'
              ? current[nodeId]
              : defaultCollapsedForStatus(nodeRecord.status)
          return { ...current, [nodeId]: !currentValue }
        })
      },
      createChild: (nodeId) => {
        void handlerRef.current.onCreateChild(nodeId)
      },
      split: (nodeId, mode) => {
        void handlerRef.current.onSplitNode(nodeId, mode)
      },
      openBreadcrumb: (nodeId) => {
        void handlerRef.current.onOpenBreadcrumb(nodeId)
      },
      finishTask: (nodeId) => {
        void handlerRef.current.onFinishTask(nodeId)
      },
      infoClick: (nodeId) => {
        setFocusedNodeId((prev) => (prev === nodeId ? null : nodeId))
        void handlerRef.current.onSelectNode(nodeId, true)
      },
    }),
    [nodeById],
  )
  const rootNode = useMemo(
    () => nodeById.get(snapshot.tree_state.root_node_id) ?? null,
    [nodeById, snapshot.tree_state.root_node_id],
  )
  const hasInvalidRootNode = rootNode === null

  const parentById = useMemo(
    () =>
      new Map(
        snapshot.tree_state.node_registry.map(
          (node) => [node.node_id, node.parent_id ?? null] as const,
        ),
      ),
    [snapshot.tree_state.node_registry],
  )

  const activeChildrenById = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const node of snapshot.tree_state.node_registry) {
      const activeChildren = node.child_ids
        .map((childId) => nodeById.get(childId))
        .filter((child): child is NodeRecord => Boolean(child && !child.is_superseded))
        .sort((left, right) => left.display_order - right.display_order)
        .map((child) => child.node_id)
      map.set(node.node_id, activeChildren)
    }
    return map
  }, [nodeById, snapshot.tree_state.node_registry])

  const collapsedById = useMemo(() => {
    const map = new Map<string, boolean>()
    for (const node of snapshot.tree_state.node_registry) {
      const override = collapseOverrides[node.node_id]
      map.set(
        node.node_id,
        typeof override === 'boolean' ? override : defaultCollapsedForStatus(node.status),
      )
    }
    return map
  }, [collapseOverrides, snapshot.tree_state.node_registry])

  const visibleChildrenById = useMemo(() => {
    const map = new Map<string, string[]>()
    for (const node of snapshot.tree_state.node_registry) {
      map.set(
        node.node_id,
        collapsedById.get(node.node_id) ? [] : (activeChildrenById.get(node.node_id) ?? []),
      )
    }
    return map
  }, [activeChildrenById, collapsedById, snapshot.tree_state.node_registry])

  const directHiddenChildrenById = useMemo(() => {
    const map = new Map<string, number>()
    for (const node of snapshot.tree_state.node_registry) {
      map.set(
        node.node_id,
        collapsedById.get(node.node_id) ? (activeChildrenById.get(node.node_id) ?? []).length : 0,
      )
    }
    return map
  }, [activeChildrenById, collapsedById, snapshot.tree_state.node_registry])

  const rootIds = useMemo(() => {
    if (!rootNode) {
      return []
    }
    const nodes = [...snapshot.tree_state.node_registry].sort(
      (left, right) => left.depth - right.depth || left.display_order - right.display_order,
    )
    const secondaryRoots = nodes
      .filter(
        (node) =>
          node.node_id !== snapshot.tree_state.root_node_id &&
          (!node.parent_id || !nodeById.has(node.parent_id)),
      )
      .map((node) => node.node_id)
    return [snapshot.tree_state.root_node_id, ...secondaryRoots]
  }, [nodeById, rootNode, snapshot.tree_state.node_registry, snapshot.tree_state.root_node_id])

  const visibleNodeIds = useMemo(() => {
    const visible = new Set<string>()
    const visit = (nodeId: string) => {
      if (visible.has(nodeId)) {
        return
      }
      visible.add(nodeId)
      for (const childId of visibleChildrenById.get(nodeId) ?? []) {
        visit(childId)
      }
    }
    if (rootNode) {
      visit(snapshot.tree_state.root_node_id)
    }
    for (const rootId of rootIds) {
      if (rootId !== snapshot.tree_state.root_node_id) {
        visit(rootId)
      }
    }
    return visible
  }, [rootIds, rootNode, snapshot.tree_state.root_node_id, visibleChildrenById])

  const selectedNode = useMemo(() => {
    if (!rootNode) {
      return null
    }
    const effectiveSelectedId = findVisibleSelectionFallback(
      selectedNodeId,
      visibleNodeIds,
      parentById,
      snapshot.tree_state.root_node_id,
    )
    return nodeById.get(effectiveSelectedId) ?? nodeById.get(snapshot.tree_state.root_node_id) ?? null
  }, [nodeById, parentById, rootNode, selectedNodeId, snapshot.tree_state.root_node_id, visibleNodeIds])

  useEffect(() => {
    if (!rootNode) {
      return
    }
    const nextSelectedId = selectedNode?.node_id ?? snapshot.tree_state.root_node_id
    if (nextSelectedId !== selectedNodeId) {
      void onSelectNode(nextSelectedId, false)
    }
  }, [onSelectNode, rootNode, selectedNode?.node_id, selectedNodeId, snapshot.tree_state.root_node_id])

  useEffect(() => {
    if (!focusedNodeId) {
      return
    }
    if (!nodeById.has(focusedNodeId)) {
      setFocusedNodeId(null)
    }
  }, [focusedNodeId, nodeById])

  useEffect(() => {
    if (!isFullscreen) {
      return undefined
    }
    function handleEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setIsFullscreen(false)
      }
    }
    document.addEventListener('keydown', handleEscape)
    return () => document.removeEventListener('keydown', handleEscape)
  }, [isFullscreen])

  const layout = useMemo(
    () => buildTreeLayoutPositions({ nodeById, rootIds, visibleChildrenById }),
    [nodeById, rootIds, visibleChildrenById],
  )

  const flowNodes = useMemo<Node<GraphNodeData>[]>(() => {
    return snapshot.tree_state.node_registry
      .filter(
        (node) => node.node_id === snapshot.tree_state.root_node_id || visibleNodeIds.has(node.node_id),
      )
      .map((node) => ({
        id: node.node_id,
        type: 'graphNode',
        className: 'nopan',
        position: layout.get(node.node_id) ?? { x: node.depth * 350, y: 0 },
        draggable: false,
        selectable: false,
        data: {
          node,
          isCurrent: snapshot.tree_state.active_node_id === node.node_id,
          isSelected: selectedNode?.node_id === node.node_id,
          isCollapsed: collapsedById.get(node.node_id) ?? false,
          directHiddenChildrenCount: directHiddenChildrenById.get(node.node_id) ?? 0,
          canCreateChild: node.status !== 'done' && !node.is_superseded,
          canFinishTask:
            codexAvailable &&
            !node.is_superseded &&
            (activeChildrenById.get(node.node_id) ?? []).length === 0 &&
            (node.status === 'ready' || node.status === 'in_progress'),
          canSplit:
            codexAvailable &&
            !node.is_superseded &&
            node.status !== 'done' &&
            (activeChildrenById.get(node.node_id) ?? []).length === 0,
          canOpenBreadcrumb: codexAvailable,
          isSplitting: splitStatus === 'active' && splittingNodeId === node.node_id,
          isSplitDisabled: splitStatus === 'active',
        },
      }))
  }, [
    activeChildrenById,
    codexAvailable,
    collapsedById,
    directHiddenChildrenById,
    layout,
    selectedNode?.node_id,
    splitStatus,
    splittingNodeId,
    snapshot.tree_state.active_node_id,
    snapshot.tree_state.node_registry,
    snapshot.tree_state.root_node_id,
    visibleNodeIds,
  ])

  const flowEdges = useMemo<Edge[]>(() => {
    const visibleSet = new Set(flowNodes.map((node) => node.id))
    return snapshot.tree_state.node_registry.flatMap((node) =>
      (visibleChildrenById.get(node.node_id) ?? [])
        .filter((childId) => visibleSet.has(node.node_id) && visibleSet.has(childId))
        .map((childId) => ({
          id: `e-${node.node_id}-${childId}`,
          source: node.node_id,
          target: childId,
          type: 'smoothstep',
          style: { stroke: 'var(--color-edge)', strokeWidth: 2.4 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: 'var(--color-edge)',
          },
        })),
    )
  }, [flowNodes, snapshot.tree_state.node_registry, visibleChildrenById])

  const fitKey = useMemo(
    () =>
      flowNodes
        .map((node) => `${node.id}:${node.position.x}:${node.position.y}:${node.data.isCollapsed ? 'c' : 'o'}`)
        .join('|'),
    [flowNodes],
  )

  useEffect(() => {
    if (!flowInstance || flowNodes.length === 0 || focusedNodeId) {
      return undefined
    }
    const handle = window.setTimeout(() => {
      void flowInstance.fitView({
        padding: 0.18,
        duration: isFullscreen ? 0 : 180,
        maxZoom: 1.12,
      })
    }, 120)
    return () => window.clearTimeout(handle)
  }, [fitKey, flowInstance, flowNodes.length, isFullscreen, focusedNodeId])

  useEffect(() => {
    if (!flowInstance || !focusedNodeId) {
      return undefined
    }
    const id = focusedNodeId
    const handle = window.setTimeout(() => {
      const shell = graphShellRef.current
      const flowViewport = shell?.querySelector('.react-flow__viewport') as HTMLElement | null
      const flowPaneW = flowViewport?.clientWidth
      const detailEl = shell?.querySelector('[data-graph-detail-panel]') as HTMLElement | null
      const measuredDetailW = detailEl?.getBoundingClientRect().width
      const rightReserve = graphDetailPanelRightReservePx(
        window.innerWidth,
        isFullscreen,
        measuredDetailW,
        flowPaneW,
      )
      void flowInstance.fitView({
        nodes: [{ id }],
        padding: {
          top: 0.12,
          bottom: 0.12,
          left: 0.12,
          right: `${rightReserve}px`,
        },
        duration: isFullscreen ? 0 : 200,
        maxZoom: 1.12,
      })
    }, 80)
    return () => window.clearTimeout(handle)
  }, [flowInstance, focusedNodeId, isFullscreen])

  function handleFlowNodePointerEvents() {
    return undefined
  }

  const focusedNode = focusedNodeId ? nodeById.get(focusedNodeId) ?? null : null

  return (
    <div
      ref={graphShellRef}
      className={`${styles.graphShell} ${isFullscreen ? styles.graphShellFullscreen : ''}`}
    >
      {hasInvalidRootNode ? (
        <div className={styles.invalidState} role="alert" data-testid="graph-invalid-snapshot">
          <h3>Graph data is invalid</h3>
          <p>The project snapshot is missing its root node, so the graph cannot be rendered safely.</p>
        </div>
      ) : (
        <GraphNodeActionsProvider value={graphNodeActions}>
          <ReactFlow
            fitView
            proOptions={{ hideAttribution: true }}
            nodes={flowNodes}
            edges={flowEdges}
            nodeTypes={nodeTypes}
            onlyRenderVisibleElements
            nodesDraggable={false}
            nodesConnectable={false}
            minZoom={0.2}
            maxZoom={1.35}
            onInit={setFlowInstance}
            onNodeClick={handleFlowNodePointerEvents}
          >
            <Background color="var(--color-border-strong)" gap={24} size={1} />
            <Controls showInteractive={false} position="bottom-right" />

            <Panel position="bottom-left">
              <div className={styles.controlStack}>
                <button
                  type="button"
                  className={styles.fullscreenButton}
                  onClick={() => setIsFullscreen((current) => !current)}
                >
                  {isFullscreen ? 'Exit Fullscreen' : 'Fullscreen'}
                </button>
                <button
                  type="button"
                  className={styles.resetButton}
                  disabled={isResetDisabled}
                  onClick={() => void onResetProject()}
                >
                  {isResettingProject ? 'Resetting...' : 'Reset to Root'}
                </button>
              </div>
            </Panel>

            {focusedNode ? (
              <Panel
                position="top-right"
                className={styles.detailPanel}
                data-graph-detail-panel
              >
                <NodeDetailCard
                  projectId={snapshot.project.id}
                  node={focusedNode}
                  variant="graph"
                  showClose
                  onClose={() => setFocusedNodeId(null)}
                />
              </Panel>
            ) : null}
          </ReactFlow>
        </GraphNodeActionsProvider>
      )}
    </div>
  )
}
