import { useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  Background,
  Controls,
  MarkerType,
  Panel,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { NodeRecord, Snapshot, SplitJobStatus, SplitMode } from '../../api/types'
import { NodeDetailCard } from '../node/NodeDetailCard'
import { indexToReviewLetter } from '../../utils/reviewSiblingLabels'
import {
  GraphNodeActionsProvider,
  type GraphNodeActions,
} from './graphNodeActionsContext'
import { GraphNode, type GraphNodeData } from './GraphNode'
import { GhostGraphNode, type GhostGraphNodeData } from './GhostGraphNode'
import { ReviewGraphNode, type ReviewGraphNodeData } from './ReviewGraphNode'
import { buildReviewOverlayPositions, buildTreeLayoutPositions, TREE_DEPTH_STEP_PX } from './treeGraphLayout'
import styles from './TreeGraph.module.css'

const nodeTypes = {
  graphNode: GraphNode,
  reviewNode: ReviewGraphNode,
  ghostNode: GhostGraphNode,
}

const SYNTHETIC_REVIEW_PREFIX = 'review::'
const REVIEW_EDGE_STROKE = 'var(--color-accent)'
const STRUCTURAL_EDGE_STROKE = 'var(--graph-edge-stroke)'

/** Slightly larger than React Flow default (12.5) so arrowheads match thicker edges. */
const EDGE_ARROW_MARKER = { width: 15, height: 15 } as const

type FlowEdgeData = {
  kind: 'structural' | 'review-child' | 'review-return' | 'ghost-review'
  parentId: string
}

/** Default fit when graph bounds change without a branch toggle (e.g. snapshot load). */
const FIT_VIEW_ANIMATION_MS = 320
/** Longer pan/zoom after expand/collapse so the viewport does not feel like it snaps. */
const FIT_VIEW_BRANCH_TOGGLE_MS = 560
/** Detail panel open/resize, between default and branch toggle. */
const FIT_VIEW_DETAIL_MS = 420

/** Caps automatic fitView so the graph does not land too zoomed-in (lower = more breathing room). */
const FIT_VIEW_MAX_ZOOM_FULL = 0.92
const FIT_VIEW_MAX_ZOOM_FOCUS = 0.88
/** "Set as current root" fits the subtree, use extra padding + lower max zoom so it does not feel tight. */
const FIT_VIEW_MAX_ZOOM_GRAPH_ROOT = 0.78
const FIT_VIEW_PADDING_FULL = 0.22
const FIT_VIEW_PADDING_FOCUS = 0.26
const FIT_VIEW_PADDING_GRAPH_ROOT = 0.36

/**
 * After closing node details, block full-graph fitView until this many ms have passed.
 * A counter is not enough when the user clicks open/close rapidly (opens reset the counter, reflows vary).
 * Each close extends the deadline so spamming close stays protected.
 */
const SUPPRESS_FULL_GRAPH_FIT_MS_AFTER_DETAIL_CLOSE = 1400

function easeInOutQuint(t: number): number {
  return t < 0.5 ? 16 * t * t * t * t * t : 1 - Math.pow(-2 * t + 2, 5) / 2
}

function resolveFitViewDurationMs(baseMs: number, isFullscreen: boolean): number {
  if (baseMs <= 0) {
    return 0
  }
  return isFullscreen ? Math.max(240, Math.round(baseMs * 0.78)) : baseMs
}

function fitViewSmoothOpts(
  isFullscreen: boolean,
  options?: {
    durationMs?: number
    ease?: (t: number) => number
  },
) {
  const durationMs = options?.durationMs ?? FIT_VIEW_ANIMATION_MS
  const ease = options?.ease ?? easeInOutQuint
  return {
    duration: resolveFitViewDurationMs(durationMs, isFullscreen),
    ease,
  }
}

function scheduleAfterReflow(run: () => void): () => void {
  let id1 = 0
  let id2 = 0
  id1 = requestAnimationFrame(() => {
    id2 = requestAnimationFrame(() => {
      run()
    })
  })
  return () => {
    cancelAnimationFrame(id1)
    cancelAnimationFrame(id2)
  }
}

/** React Flow `.react-flow__panel` margin in TreeGraph.module.css */
const REACT_FLOW_PANEL_MARGIN_PX = 12

/** Expanded sidebar width, keep in sync with `.sidebar` in Sidebar.module.css */
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
  revealSplitNodeId?: string | null
  isCreatingNode: boolean
  isResettingProject: boolean
  isResetDisabled: boolean
  codexAvailable: boolean
  onSelectNode: (nodeId: string, persist?: boolean) => Promise<void>
  onCreateChild: (parentId: string) => Promise<void>
  onCreateTask: (parentId: string, description: string) => Promise<string | null>
  onSplitNode: (nodeId: string, mode: SplitMode) => Promise<void>
  onOpenBreadcrumb: (nodeId: string) => Promise<void>
  onResetProject: () => Promise<void>
}

function defaultCollapsedForStatus(status: NodeRecord['status']): boolean {
  return status === 'locked' || status === 'done'
}

/**
 * 1-based index among visible siblings under the same parent (same "layer" in the graph).
 * Top-level roots use `effectiveRootIds` order when the full forest is shown; subtree mode uses a single root.
 */
function siblingLayerIndex1Based(
  nodeId: string,
  visibleNodeIds: Set<string>,
  parentById: Map<string, string | null>,
  visibleChildrenById: Map<string, string[]>,
  effectiveRootIds: string[],
  graphViewRootId: string | null,
): number {
  const parentId = parentById.get(nodeId) ?? null
  const parentVisible = parentId !== null && visibleNodeIds.has(parentId)

  if (parentVisible) {
    const siblings = visibleChildrenById.get(parentId) ?? []
    const idx = siblings.indexOf(nodeId)
    return idx >= 0 ? idx + 1 : 1
  }

  const roots =
    graphViewRootId !== null && visibleNodeIds.has(graphViewRootId)
      ? [graphViewRootId]
      : effectiveRootIds.filter((id) => visibleNodeIds.has(id))
  const idx = roots.indexOf(nodeId)
  return idx >= 0 ? idx + 1 : 1
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
  revealSplitNodeId = null,
  isCreatingNode: _isCreatingNode,
  isResettingProject,
  isResetDisabled,
  codexAvailable,
  onSelectNode,
  onCreateChild,
  onCreateTask,
  onSplitNode,
  onOpenBreadcrumb,
  onResetProject,
}: Props) {
  const [collapseOverrides, setCollapseOverrides] = useState<Record<string, boolean>>({})
  const [isFullscreen, setIsFullscreen] = useState(false)
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null)
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null)
  const [createTaskParentId, setCreateTaskParentId] = useState<string | null>(null)
  const [createTaskDescription, setCreateTaskDescription] = useState('')
  const [createTaskSubmitting, setCreateTaskSubmitting] = useState(false)
  const [createTaskError, setCreateTaskError] = useState<string | null>(null)
  /** Subtree-only graph view; null = show full project tree. */
  const [graphViewRootId, setGraphViewRootId] = useState<string | null>(null)
  const graphShellRef = useRef<HTMLDivElement | null>(null)
  /** After expand/collapse toggle, next fitView targets this node so the viewport stays on the toggled card. */
  const branchToggleFocusNodeIdRef = useRef<string | null>(null)
  /** After "Set as current root", fitView to that node (runs even when detail panel is open). */
  const graphViewRootFitPendingRef = useRef<string | null>(null)
  /** After "Unset current root", fit the full project tree (runs before focused-node early return). */
  const graphViewRootUnsetFitPendingRef = useRef(false)
  /** While `performance.now()` is below this, skip full-graph fitView (after closing details). */
  const suppressFullGraphFitUntilRef = useRef(0)
  const previousSplitStatusRef = useRef<SplitJobStatus>(splitStatus)
  const lastSplitNodeIdRef = useRef<string | null>(splittingNodeId)
  const lastRevealedSplitNodeIdRef = useRef<string | null>(null)
  const handlerRef = useRef({
    onSelectNode,
    onCreateChild,
    onCreateTask,
    onSplitNode,
    onOpenBreadcrumb,
  })
  handlerRef.current = {
    onSelectNode,
    onCreateChild,
    onCreateTask,
    onSplitNode,
    onOpenBreadcrumb,
  }

  const nodeById = useMemo(
    () => new Map(snapshot.tree_state.node_registry.map((node) => [node.node_id, node])),
    [snapshot.tree_state.node_registry],
  )

  const graphNodeActions = useMemo<GraphNodeActions>(
    () => ({
      graphViewRootId,
      setGraphViewRoot: (nodeId) => {
        setGraphViewRootId(nodeId)
        if (nodeId) {
          graphViewRootFitPendingRef.current = nodeId
          graphViewRootUnsetFitPendingRef.current = false
        } else {
          graphViewRootUnsetFitPendingRef.current = true
          suppressFullGraphFitUntilRef.current = 0
        }
      },
      selectNode: (nodeId) => {
        void handlerRef.current.onSelectNode(nodeId, true)
      },
      toggleCollapse: (nodeId) => {
        setCollapseOverrides((current) => {
          const nodeRecord = nodeById.get(nodeId)
          if (!nodeRecord) {
            return current
          }
          const isCollapsedNow =
            typeof current[nodeId] === 'boolean'
              ? current[nodeId]
              : defaultCollapsedForStatus(nodeRecord.status)
          const nextCollapsed = !isCollapsedNow
          branchToggleFocusNodeIdRef.current = nodeId
          return { ...current, [nodeId]: nextCollapsed }
        })
      },
      createChild: (nodeId) => {
        void handlerRef.current.onCreateChild(nodeId)
      },
      createTask: (nodeId) => {
        setCreateTaskParentId(nodeId)
        setCreateTaskDescription('')
        setCreateTaskError(null)
      },
      initDocsForProject: () => {
        if (typeof window !== 'undefined' && typeof window.alert === 'function') {
          window.alert('Init docs for project is a placeholder action for now.')
        }
      },
      split: (nodeId, mode) => {
        void handlerRef.current.onSplitNode(nodeId, mode)
      },
      openBreadcrumb: (nodeId) => {
        void handlerRef.current.onOpenBreadcrumb(nodeId)
      },
      infoClick: (nodeId) => {
        setFocusedNodeId((prev) => {
          if (prev === nodeId) {
            suppressFullGraphFitUntilRef.current =
              performance.now() + SUPPRESS_FULL_GRAPH_FIT_MS_AFTER_DETAIL_CLOSE
            return null
          }
          suppressFullGraphFitUntilRef.current = 0
          return nodeId
        })
        void handlerRef.current.onSelectNode(nodeId, true)
      },
    }),
    [graphViewRootId, nodeById],
  )

  const createTaskParentNode = createTaskParentId ? (nodeById.get(createTaskParentId) ?? null) : null

  function closeCreateTaskDialog() {
    if (createTaskSubmitting) {
      return
    }
    setCreateTaskParentId(null)
    setCreateTaskDescription('')
    setCreateTaskError(null)
  }

  async function submitCreateTask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!createTaskParentId) {
      return
    }
    const description = createTaskDescription.trim()
    if (!description) {
      setCreateTaskError('Task description is required.')
      return
    }

    setCreateTaskSubmitting(true)
    setCreateTaskError(null)
    try {
      const createdNodeId = await onCreateTask(createTaskParentId, description)
      if (!createdNodeId) {
        setCreateTaskError('Could not create task. Please retry.')
        return
      }
      setCreateTaskParentId(null)
      setCreateTaskDescription('')
      setCreateTaskError(null)
      await onOpenBreadcrumb(createdNodeId)
    } catch (error) {
      setCreateTaskError(error instanceof Error ? error.message : 'Could not create task.')
    } finally {
      setCreateTaskSubmitting(false)
    }
  }

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

  const effectiveRootIds = useMemo(() => {
    if (graphViewRootId && nodeById.has(graphViewRootId)) {
      return [graphViewRootId]
    }
    return rootIds
  }, [graphViewRootId, nodeById, rootIds])

  const selectionFallbackRootId =
    graphViewRootId && nodeById.has(graphViewRootId)
      ? graphViewRootId
      : snapshot.tree_state.root_node_id

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
    if (graphViewRootId && nodeById.has(graphViewRootId)) {
      visit(graphViewRootId)
      return visible
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
  }, [
    graphViewRootId,
    nodeById,
    rootIds,
    rootNode,
    snapshot.tree_state.root_node_id,
    visibleChildrenById,
  ])

  const siblingLayerIndexByNodeId = useMemo(() => {
    const map = new Map<string, number>()
    for (const id of visibleNodeIds) {
      map.set(
        id,
        siblingLayerIndex1Based(
          id,
          visibleNodeIds,
          parentById,
          visibleChildrenById,
          effectiveRootIds,
          graphViewRootId,
        ),
      )
    }
    return map
  }, [
    effectiveRootIds,
    graphViewRootId,
    parentById,
    visibleChildrenById,
    visibleNodeIds,
  ])

  const selectedNode = useMemo(() => {
    if (!rootNode) {
      return null
    }
    const effectiveSelectedId = findVisibleSelectionFallback(
      selectedNodeId,
      visibleNodeIds,
      parentById,
      selectionFallbackRootId,
    )
    return nodeById.get(effectiveSelectedId) ?? nodeById.get(selectionFallbackRootId) ?? null
  }, [nodeById, parentById, rootNode, selectedNodeId, selectionFallbackRootId, visibleNodeIds])

  useEffect(() => {
    if (!rootNode) {
      return
    }
    const nextSelectedId = selectedNode?.node_id ?? selectionFallbackRootId
    if (nextSelectedId !== selectedNodeId) {
      void onSelectNode(nextSelectedId, false)
    }
  }, [onSelectNode, rootNode, selectedNode?.node_id, selectedNodeId, selectionFallbackRootId])

  useEffect(() => {
    if (graphViewRootId && !nodeById.has(graphViewRootId)) {
      setGraphViewRootId(null)
    }
  }, [graphViewRootId, nodeById])

  useEffect(() => {
    if (!focusedNodeId) {
      return
    }
    if (!nodeById.has(focusedNodeId)) {
      setFocusedNodeId(null)
    }
  }, [focusedNodeId, nodeById])

  useEffect(() => {
    if (splitStatus === 'active' && splittingNodeId) {
      lastSplitNodeIdRef.current = splittingNodeId
    }
  }, [splittingNodeId, splitStatus])

  useEffect(() => {
    if (!revealSplitNodeId || lastRevealedSplitNodeIdRef.current === revealSplitNodeId) {
      return
    }
    lastRevealedSplitNodeIdRef.current = revealSplitNodeId
    setGraphViewRootId(null)
    graphViewRootUnsetFitPendingRef.current = true
    setFocusedNodeId(null)
    setCreateTaskParentId(null)
    setCreateTaskError(null)
    setCollapseOverrides((current) =>
      current[revealSplitNodeId] === false ? current : { ...current, [revealSplitNodeId]: false },
    )
    suppressFullGraphFitUntilRef.current = 0
  }, [revealSplitNodeId])

  useEffect(() => {
    const previousStatus = previousSplitStatusRef.current
    previousSplitStatusRef.current = splitStatus

    if (previousStatus !== 'active') {
      return
    }

    if (splitStatus === 'idle') {
      const completedSplitNodeId = lastSplitNodeIdRef.current
      lastSplitNodeIdRef.current = null
      if (!completedSplitNodeId) {
        return
      }

      setCreateTaskParentId(null)
      setCreateTaskError(null)
      setGraphViewRootId(null)
      graphViewRootUnsetFitPendingRef.current = true
      setFocusedNodeId(null)
      setCollapseOverrides((current) =>
        current[completedSplitNodeId] === false
          ? current
          : { ...current, [completedSplitNodeId]: false },
      )
      suppressFullGraphFitUntilRef.current = 0
      return
    }

    if (splitStatus === 'failed') {
      lastSplitNodeIdRef.current = null
    }
  }, [splitStatus])

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

  // Ghost siblings: unmaterialized pending siblings from review node manifests
  const ghostSiblingMap = useMemo(() => {
    const map = new Map<
      string,
      { id: string; title: string; index: number; objective: string }[]
    >()
    for (const node of snapshot.tree_state.node_registry) {
      if (node.node_kind !== 'review' || !node.review_summary?.sibling_manifest) continue
      if (!node.parent_id) continue
      const pending = node.review_summary.sibling_manifest
        .filter((s) => s.status === 'pending')
        .map((s) => ({
          id: `ghost::${node.parent_id}::${s.index}`,
          title: s.title,
          index: s.index,
          objective: (s.objective ?? '').trim(),
        }))
      if (pending.length > 0) {
        map.set(node.parent_id, pending)
      }
    }
    return map
  }, [snapshot.tree_state.node_registry])

  const { nodePositions, ghostPositions } = useMemo(
    () =>
      buildTreeLayoutPositions({
        nodeById,
        rootIds: effectiveRootIds,
        visibleChildrenById,
        depthBaseNodeId: graphViewRootId,
        ghostSiblingsByParent: ghostSiblingMap,
      }),
    [nodeById, effectiveRootIds, ghostSiblingMap, graphViewRootId, visibleChildrenById],
  )

  const reviewOverlayPositions = useMemo(
    () =>
      buildReviewOverlayPositions({
        nodeById,
        visibleChildrenById,
        treePositions: nodePositions,
      }),
    [nodeById, nodePositions, visibleChildrenById],
  )

  const realFlowNodes = useMemo<Node<GraphNodeData>[]>(() => {
    return snapshot.tree_state.node_registry
      .filter((node) => visibleNodeIds.has(node.node_id) && node.node_kind !== 'review')
      .map((node) => ({
        id: node.node_id,
        type: 'graphNode',
        className: 'nopan',
        position: nodePositions.get(node.node_id) ?? { x: 0, y: node.depth * TREE_DEPTH_STEP_PX },
        draggable: false,
        selectable: false,
        data: {
          node,
          isInitNode: Boolean(node.is_init_node),
          siblingLayerIndex: siblingLayerIndexByNodeId.get(node.node_id) ?? 1,
          isCurrent: snapshot.tree_state.active_node_id === node.node_id,
          isSelected: selectedNode?.node_id === node.node_id,
          isCollapsed: collapsedById.get(node.node_id) ?? false,
          directHiddenChildrenCount: directHiddenChildrenById.get(node.node_id) ?? 0,
          canCreateChild: !node.is_init_node && node.status !== 'done' && !node.is_superseded,
          canCreateTask:
            Boolean(node.is_init_node) &&
            node.status !== 'done' &&
            !node.is_superseded &&
            splitStatus !== 'active',
          canSplit:
            codexAvailable &&
            !node.is_init_node &&
            !node.is_superseded &&
            node.status !== 'done' &&
            (activeChildrenById.get(node.node_id) ?? []).length === 0 &&
            (node.workflow?.frame_confirmed ?? false) &&
            node.workflow?.active_step === 'spec',
          canOpenBreadcrumb: true,
          isSplitting: splitStatus === 'active' && splittingNodeId === node.node_id,
          isSplitDisabled: splitStatus === 'active',
          executionStatus: node.workflow?.execution_status ?? null,
          graphViewRootId,
        },
      }))
  }, [
    activeChildrenById,
    codexAvailable,
    collapsedById,
    directHiddenChildrenById,
    graphViewRootId,
    nodePositions,
    selectedNode?.node_id,
    siblingLayerIndexByNodeId,
    splitStatus,
    splittingNodeId,
    snapshot.tree_state.active_node_id,
    snapshot.tree_state.node_registry,
    visibleNodeIds,
  ])

  const reviewFlowNodes = useMemo<Node<ReviewGraphNodeData>[]>(() => {
    const nodes: Node<ReviewGraphNodeData>[] = []
    for (const [reviewId, position] of reviewOverlayPositions.entries()) {
      const isSynthetic = reviewId.startsWith(SYNTHETIC_REVIEW_PREFIX)
      const parentId = isSynthetic
        ? reviewId.slice(SYNTHETIC_REVIEW_PREFIX.length)
        : nodeById.get(reviewId)?.parent_id ?? ''
      const parent = nodeById.get(parentId)
      if (!parent) {
        continue
      }
      const realReviewNode = isSynthetic ? null : nodeById.get(reviewId)
      const summary = realReviewNode?.review_summary
      const checkpointCount = summary?.checkpoint_count ?? 0

      const siblingEntries = (summary?.sibling_manifest ?? []).map((sibling) => ({
        index: sibling.index,
        title: sibling.title,
        letter: indexToReviewLetter(sibling.index),
        status: sibling.status,
      }))

      nodes.push({
        id: reviewId,
        type: 'reviewNode',
        className: 'nopan',
        position,
        draggable: false,
        selectable: false,
        data: {
          parentNodeId: parent.node_id,
          parentTitle: parent.title,
          parentHierarchicalNumber: parent.hierarchical_number,
          checkpointCount,
          rollupStatus: summary?.rollup_status ?? null,
          pendingSiblingCount: summary?.pending_sibling_count ?? 0,
          siblingEntries,
          reviewNodeId: isSynthetic ? null : reviewId,
          canOpenBreadcrumb: !isSynthetic,
        },
      })
    }
    return nodes
  }, [nodeById, reviewOverlayPositions])

  const ghostFlowNodes = useMemo<Node<GhostGraphNodeData>[]>(() => {
    const nodes: Node<GhostGraphNodeData>[] = []
    for (const [parentId, siblings] of ghostSiblingMap) {
      const parent = nodeById.get(parentId)
      if (!parent) continue
      for (const sibling of siblings) {
        const position = ghostPositions.get(sibling.id)
        if (!position) continue
        nodes.push({
          id: sibling.id,
          type: 'ghostNode',
          className: 'nopan',
          position,
          draggable: false,
          selectable: false,
          data: {
            parentId,
            title: sibling.title,
            siblingIndex: sibling.index,
            parentHierarchicalNumber: parent.hierarchical_number,
            objective: sibling.objective,
          },
        })
      }
    }
    return nodes
  }, [ghostSiblingMap, ghostPositions, nodeById])

  const flowNodes = useMemo<Array<Node<GraphNodeData | ReviewGraphNodeData | GhostGraphNodeData>>>(
    () => [...realFlowNodes, ...reviewFlowNodes, ...ghostFlowNodes],
    [realFlowNodes, reviewFlowNodes, ghostFlowNodes],
  )

  const flowEdges = useMemo<Edge<FlowEdgeData>[]>(() => {
    const visibleSet = new Set(flowNodes.map((node) => node.id))

    const structuralEdges = snapshot.tree_state.node_registry.flatMap((node) =>
      (visibleChildrenById.get(node.node_id) ?? [])
        .filter((childId) => visibleSet.has(node.node_id) && visibleSet.has(childId))
        .map((childId) => ({
          id: `e-${node.node_id}-${childId}`,
          source: node.node_id,
          target: childId,
          sourceHandle: 'out',
          targetHandle: 'in',
          data: {
            kind: 'structural' as const,
            parentId: node.node_id,
          },
          type: 'straight',
          sourcePosition: Position.Bottom,
          targetPosition: Position.Top,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: STRUCTURAL_EDGE_STROKE,
            ...EDGE_ARROW_MARKER,
          },
          style: {
            stroke: STRUCTURAL_EDGE_STROKE,
            strokeWidth: 'var(--graph-edge-width)',
            strokeLinecap: 'round' as const,
          },
        })),
    )

    const reviewEdges = [...reviewOverlayPositions.keys()].flatMap((reviewId) => {
      const isSynthetic = reviewId.startsWith(SYNTHETIC_REVIEW_PREFIX)
      const parentId = isSynthetic
        ? reviewId.slice(SYNTHETIC_REVIEW_PREFIX.length)
        : nodeById.get(reviewId)?.parent_id ?? ''
      const reviewPosition = reviewOverlayPositions.get(reviewId)
      const childIds = (visibleChildrenById.get(parentId) ?? []).filter((childId) =>
        visibleSet.has(childId),
      )
      if (
        childIds.length === 0 ||
        !reviewPosition ||
        !visibleSet.has(reviewId) ||
        !visibleSet.has(parentId)
      ) {
        return []
      }

      const inboundEdges = childIds.map((childId) => {
        return {
          id: `review-child-${childId}-${parentId}`,
          source: childId,
          target: reviewId,
          sourceHandle: 'to-review',
          targetHandle: 'in',
          data: {
            kind: 'review-child' as const,
            parentId,
          },
          type: 'straight',
          sourcePosition: Position.Top,
          targetPosition: Position.Bottom,
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: REVIEW_EDGE_STROKE,
            ...EDGE_ARROW_MARKER,
          },
          style: {
            stroke: REVIEW_EDGE_STROKE,
            strokeWidth: 'var(--graph-edge-width)',
            strokeLinecap: 'round' as const,
          },
        }
      })

      const returnEdge = {
        id: `review-return-${parentId}`,
        source: reviewId,
        target: parentId,
        sourceHandle: 'out',
        targetHandle: 'review-return',
        data: {
          kind: 'review-return' as const,
          parentId,
        },
        type: 'straight',
        sourcePosition: Position.Top,
        targetPosition: Position.Bottom,
        markerEnd: {
          type: MarkerType.ArrowClosed,
          color: REVIEW_EDGE_STROKE,
          ...EDGE_ARROW_MARKER,
        },
        style: {
          stroke: REVIEW_EDGE_STROKE,
          strokeWidth: 'var(--graph-edge-width)',
          strokeLinecap: 'round' as const,
        },
      }

      return [...inboundEdges, returnEdge]
    })

    // Dashed structural edges from parent to ghost (pending) siblings
    const ghostEdges = []
    const ghostReviewEdges = []
    for (const [parentId, siblings] of ghostSiblingMap) {
      if (!visibleSet.has(parentId)) continue

      const parentRecord = nodeById.get(parentId)
      const childIds = visibleChildrenById.get(parentId) ?? []
      const reviewNodeId = parentRecord?.review_node_id
      const useSynthetic = !reviewNodeId && childIds.length >= 2
      const reviewId =
        reviewNodeId || useSynthetic ? (reviewNodeId ?? `review::${parentId}`) : null
      const reviewVisible = reviewId !== null && visibleSet.has(reviewId)

      for (const sibling of siblings) {
        if (!ghostPositions.has(sibling.id)) continue
        ghostEdges.push({
          id: `ghost-edge-${parentId}-${sibling.id}`,
          source: parentId,
          target: sibling.id,
          sourceHandle: 'out',
          targetHandle: 'in',
          data: {
            kind: 'structural' as const,
            parentId,
          },
          type: 'straight',
          sourcePosition: Position.Bottom,
          targetPosition: Position.Top,
          style: {
            stroke: 'var(--color-text-tertiary)',
            strokeWidth: 'var(--graph-edge-width)',
            strokeDasharray: '4 3',
            strokeLinecap: 'round' as const,
            opacity: 0.45,
          },
        })

        if (reviewVisible && visibleSet.has(sibling.id)) {
          ghostReviewEdges.push({
            id: `ghost-review-${sibling.id}`,
            source: sibling.id,
            target: reviewId,
            sourceHandle: 'to-review',
            targetHandle: 'in',
            data: {
              kind: 'ghost-review' as const,
              parentId,
            },
            type: 'straight',
            sourcePosition: Position.Top,
            targetPosition: Position.Bottom,
            markerEnd: {
              type: MarkerType.ArrowClosed,
              color: REVIEW_EDGE_STROKE,
              ...EDGE_ARROW_MARKER,
            },
            style: {
              stroke: REVIEW_EDGE_STROKE,
              strokeWidth: 'var(--graph-edge-width)',
              strokeLinecap: 'round' as const,
              opacity: 0.55,
            },
          })
        }
      }
    }

    return [...structuralEdges, ...reviewEdges, ...ghostEdges, ...ghostReviewEdges]
  }, [
    flowNodes,
    ghostPositions,
    ghostSiblingMap,
    nodeById,
    nodePositions,
    reviewOverlayPositions,
    snapshot.tree_state.node_registry,
    visibleChildrenById,
  ])

  const fitKey = useMemo(
    () =>
      flowNodes
        .map((node) => `${node.id}:${node.position.x}:${node.position.y}`)
        .join('|'),
    [flowNodes],
  )

  useLayoutEffect(() => {
    if (!flowInstance || flowNodes.length === 0) {
      return undefined
    }
    if (graphViewRootUnsetFitPendingRef.current) {
      graphViewRootUnsetFitPendingRef.current = false
      suppressFullGraphFitUntilRef.current = 0
      return scheduleAfterReflow(() => {
        void flowInstance.fitView({
          padding: FIT_VIEW_PADDING_FULL,
          maxZoom: FIT_VIEW_MAX_ZOOM_FULL,
          ...fitViewSmoothOpts(isFullscreen, { durationMs: FIT_VIEW_BRANCH_TOGGLE_MS }),
        })
      })
    }
    const pendingGraphViewFit = graphViewRootFitPendingRef.current
    if (pendingGraphViewFit) {
      graphViewRootFitPendingRef.current = null
      suppressFullGraphFitUntilRef.current = 0
      return scheduleAfterReflow(() => {
        // Fit the whole visible subtree, not a single node's bounds (single-node fit zooms in too tight).
        void flowInstance.fitView({
          padding: FIT_VIEW_PADDING_GRAPH_ROOT,
          maxZoom: FIT_VIEW_MAX_ZOOM_GRAPH_ROOT,
          ...fitViewSmoothOpts(isFullscreen, { durationMs: FIT_VIEW_BRANCH_TOGGLE_MS }),
        })
      })
    }
    if (focusedNodeId) {
      branchToggleFocusNodeIdRef.current = null
      suppressFullGraphFitUntilRef.current = 0
      return undefined
    }
    const focusToggleNodeId = branchToggleFocusNodeIdRef.current
    branchToggleFocusNodeIdRef.current = null

    if (focusToggleNodeId) {
      suppressFullGraphFitUntilRef.current = 0
      return scheduleAfterReflow(() => {
        void flowInstance.fitView({
          nodes: [{ id: focusToggleNodeId }],
          padding: FIT_VIEW_PADDING_FOCUS,
          maxZoom: FIT_VIEW_MAX_ZOOM_FOCUS,
          ...fitViewSmoothOpts(isFullscreen, { durationMs: FIT_VIEW_BRANCH_TOGGLE_MS }),
        })
      })
    }

    if (performance.now() < suppressFullGraphFitUntilRef.current) {
      return undefined
    }

    return scheduleAfterReflow(() => {
      void flowInstance.fitView({
        padding: FIT_VIEW_PADDING_FULL,
        maxZoom: FIT_VIEW_MAX_ZOOM_FULL,
        ...fitViewSmoothOpts(isFullscreen),
      })
    })
  }, [fitKey, flowInstance, flowNodes.length, isFullscreen, focusedNodeId])

  useLayoutEffect(() => {
    if (!flowInstance || !focusedNodeId) {
      return undefined
    }
    const id = focusedNodeId
    return scheduleAfterReflow(() => {
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
          top: 0.14,
          bottom: 0.14,
          left: 0.14,
          right: `${rightReserve}px`,
        },
        maxZoom: FIT_VIEW_MAX_ZOOM_FOCUS,
        ...fitViewSmoothOpts(isFullscreen, { durationMs: FIT_VIEW_DETAIL_MS }),
      })
    })
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
        <>
          <GraphNodeActionsProvider value={graphNodeActions}>
            <ReactFlow
              fitView
              fitViewOptions={{
                padding: FIT_VIEW_PADDING_FULL,
                maxZoom: FIT_VIEW_MAX_ZOOM_FULL,
                ...fitViewSmoothOpts(isFullscreen),
              }}
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
              <Background color="var(--color-border-subtle)" gap={22} size={1} />
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
                    onClose={() => {
                      suppressFullGraphFitUntilRef.current =
                        performance.now() + SUPPRESS_FULL_GRAPH_FIT_MS_AFTER_DETAIL_CLOSE
                      setFocusedNodeId(null)
                    }}
                  />
                </Panel>
              ) : null}
            </ReactFlow>
          </GraphNodeActionsProvider>

          {createTaskParentId ? (
            <div
              className={styles.createTaskBackdrop}
              onClick={(event) => {
                if (event.target === event.currentTarget) {
                  closeCreateTaskDialog()
                }
              }}
            >
              <form className={styles.createTaskDialog} onSubmit={(event) => void submitCreateTask(event)}>
                <h3 className={styles.createTaskTitle}>Create A Task</h3>
                <p className={styles.createTaskSubtitle}>
                  Init node: <strong>{createTaskParentNode?.title ?? 'Project root'}</strong>
                </p>
                <label className={styles.createTaskLabel} htmlFor="create-task-description">
                  Describe this task for AI agents
                </label>
                <textarea
                  id="create-task-description"
                  className={styles.createTaskTextarea}
                  value={createTaskDescription}
                  onChange={(event) => setCreateTaskDescription(event.target.value)}
                  placeholder="Describe one concrete task..."
                  rows={5}
                  autoFocus
                />
                {createTaskError ? <p className={styles.createTaskError}>{createTaskError}</p> : null}
                <div className={styles.createTaskActions}>
                  <button
                    type="button"
                    className={styles.createTaskCancel}
                    onClick={closeCreateTaskDialog}
                    disabled={createTaskSubmitting}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className={styles.createTaskConfirm}
                    disabled={createTaskSubmitting || !createTaskDescription.trim()}
                  >
                    {createTaskSubmitting ? 'Creating...' : 'Confirm Task'}
                  </button>
                </div>
              </form>
            </div>
          ) : null}
        </>
      )}
    </div>
  )
}
