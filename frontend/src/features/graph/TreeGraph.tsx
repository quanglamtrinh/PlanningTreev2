import { useEffect, useMemo, useRef, useState } from "react";
import {
  Background,
  Controls,
  MarkerType,
  Panel,
  ReactFlow,
  type Edge,
  type Node,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { NodeRecord, Snapshot, SplitMode } from "../../api/types";
import { useProjectStore } from "../../stores/project-store";
import { TaskPanel } from "../breadcrumb/TaskPanel";
import { GraphNode, type GraphNodeData } from "./GraphNode";
import { buildTreeLayoutPositions } from "./treeGraphLayout";
import styles from "./TreeGraph.module.css";

const nodeTypes = {
  graphNode: GraphNode,
};

type Props = {
  snapshot: Snapshot;
  selectedNodeId: string | null;
  isCreatingNode: boolean;
  isSplittingNode: boolean;
  splittingNodeId: string | null;
  onSelectNode: (nodeId: string, persist?: boolean) => Promise<void>;
  onCreateChild: (parentId: string) => Promise<void>;
  onSplitNode: (
    nodeId: string,
    mode: SplitMode,
  ) => Promise<void>;
  onOpenBreadcrumb: (nodeId: string) => Promise<void>;
  onFinishTask: (nodeId: string) => Promise<void>;
};

function defaultCollapsedForStatus(status: NodeRecord["status"]): boolean {
  return status === "locked" || status === "done";
}

function findVisibleSelectionFallback(
  selectedNodeId: string | null,
  visibleNodeIds: Set<string>,
  parentById: Map<string, string | null>,
  rootNodeId: string,
): string {
  if (!selectedNodeId || visibleNodeIds.has(selectedNodeId)) {
    return selectedNodeId ?? rootNodeId;
  }

  let currentId: string | null = selectedNodeId;
  const visited = new Set<string>();
  while (currentId && !visited.has(currentId)) {
    visited.add(currentId);
    const resolvedParentId = parentById.get(currentId);
    const parentId: string | null = resolvedParentId ?? null;
    if (!parentId) {
      break;
    }
    if (visibleNodeIds.has(parentId)) {
      return parentId;
    }
    currentId = parentId;
  }

  return rootNodeId;
}

export function TreeGraph({
  snapshot,
  selectedNodeId,
  isCreatingNode: _isCreatingNode,
  isSplittingNode,
  splittingNodeId,
  onSelectNode,
  onCreateChild,
  onSplitNode,
  onOpenBreadcrumb,
  onFinishTask,
}: Props) {
  const [collapseOverrides, setCollapseOverrides] = useState<
    Record<string, boolean>
  >({});
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(
    null,
  );
  const [focusedNodeId, setFocusedNodeId] = useState<string | null>(null);
  const documentsByNode = useProjectStore((state) => state.documentsByNode);
  const agentActivityByNode = useProjectStore(
    (state) => state.agentActivityByNode,
  );
  const isLoadingDocuments = useProjectStore(
    (state) => state.isLoadingDocuments,
  );
  const isUpdatingDocument = useProjectStore(
    (state) => state.isUpdatingDocument,
  );
  const isConfirmingNode = useProjectStore((state) => state.isConfirmingNode);
  const loadNodeDocuments = useProjectStore((state) => state.loadNodeDocuments);
  const updateNodeTask = useProjectStore((state) => state.updateNodeTask);
  const confirmTask = useProjectStore((state) => state.confirmTask);
  const handlerRef = useRef({
    onSelectNode,
    onCreateChild,
    onSplitNode,
    onOpenBreadcrumb,
    onFinishTask,
  });
  handlerRef.current = {
    onSelectNode,
    onCreateChild,
    onSplitNode,
    onOpenBreadcrumb,
    onFinishTask,
  };

  const nodeById = useMemo(
    () =>
      new Map(
        snapshot.tree_state.node_registry.map((node) => [node.node_id, node]),
      ),
    [snapshot.tree_state.node_registry],
  );
  const rootNode = useMemo(
    () => nodeById.get(snapshot.tree_state.root_node_id) ?? null,
    [nodeById, snapshot.tree_state.root_node_id],
  );
  const hasInvalidRootNode = rootNode === null;

  const parentById = useMemo(
    () =>
      new Map(
        snapshot.tree_state.node_registry.map(
          (node) => [node.node_id, node.parent_id ?? null] as const,
        ),
      ),
    [snapshot.tree_state.node_registry],
  );

  const activeChildrenById = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const node of snapshot.tree_state.node_registry) {
      const activeChildren = node.child_ids
        .map((childId) => nodeById.get(childId))
        .filter((child): child is NodeRecord =>
          Boolean(child && !child.is_superseded),
        )
        .sort((left, right) => left.display_order - right.display_order)
        .map((child) => child.node_id);
      map.set(node.node_id, activeChildren);
    }
    return map;
  }, [nodeById, snapshot.tree_state.node_registry]);

  const collapsedById = useMemo(() => {
    const map = new Map<string, boolean>();
    for (const node of snapshot.tree_state.node_registry) {
      const override = collapseOverrides[node.node_id];
      map.set(
        node.node_id,
        typeof override === "boolean"
          ? override
          : defaultCollapsedForStatus(node.status),
      );
    }
    return map;
  }, [collapseOverrides, snapshot.tree_state.node_registry]);

  const visibleChildrenById = useMemo(() => {
    const map = new Map<string, string[]>();
    for (const node of snapshot.tree_state.node_registry) {
      map.set(
        node.node_id,
        collapsedById.get(node.node_id)
          ? []
          : (activeChildrenById.get(node.node_id) ?? []),
      );
    }
    return map;
  }, [activeChildrenById, collapsedById, snapshot.tree_state.node_registry]);

  const directHiddenChildrenById = useMemo(() => {
    const map = new Map<string, number>();
    for (const node of snapshot.tree_state.node_registry) {
      map.set(
        node.node_id,
        collapsedById.get(node.node_id)
          ? (activeChildrenById.get(node.node_id) ?? []).length
          : 0,
      );
    }
    return map;
  }, [activeChildrenById, collapsedById, snapshot.tree_state.node_registry]);

  const canSplitById = useMemo(() => {
    const map = new Map<string, boolean>();
    for (const node of snapshot.tree_state.node_registry) {
      if (node.is_superseded || node.status === "done") {
        map.set(node.node_id, false);
        continue;
      }

      const activeChildren = activeChildrenById.get(node.node_id) ?? [];
      if (activeChildren.length === 0) {
        map.set(node.node_id, true);
        continue;
      }

      const stack = [...activeChildren].reverse();
      const visited = new Set<string>();
      let canSplit = true;
      while (stack.length > 0) {
        const currentId = stack.pop();
        if (!currentId || visited.has(currentId)) {
          continue;
        }
        visited.add(currentId);
        const currentNode = nodeById.get(currentId);
        if (!currentNode || currentNode.is_superseded) {
          continue;
        }
        if (
          currentNode.status === "done" ||
          currentNode.status === "in_progress"
        ) {
          canSplit = false;
          break;
        }
        const descendants = activeChildrenById.get(currentId) ?? [];
        for (let index = descendants.length - 1; index >= 0; index -= 1) {
          stack.push(descendants[index]);
        }
      }

      map.set(node.node_id, canSplit);
    }
    return map;
  }, [activeChildrenById, nodeById, snapshot.tree_state.node_registry]);

  const rootIds = useMemo(() => {
    if (!rootNode) {
      return [];
    }

    const nodes = [...snapshot.tree_state.node_registry].sort(
      (left, right) =>
        left.depth - right.depth || left.display_order - right.display_order,
    );
    const secondaryRoots = nodes
      .filter(
        (node) =>
          node.node_id !== snapshot.tree_state.root_node_id &&
          (!node.parent_id || !nodeById.has(node.parent_id)),
      )
      .map((node) => node.node_id);
    return [snapshot.tree_state.root_node_id, ...secondaryRoots];
  }, [
    nodeById,
    rootNode,
    snapshot.tree_state.node_registry,
    snapshot.tree_state.root_node_id,
  ]);

  const visibleNodeIds = useMemo(() => {
    const visible = new Set<string>();

    const visit = (nodeId: string) => {
      if (visible.has(nodeId)) {
        return;
      }
      visible.add(nodeId);
      for (const childId of visibleChildrenById.get(nodeId) ?? []) {
        visit(childId);
      }
    };

    if (rootNode) {
      visit(snapshot.tree_state.root_node_id);
    }

    for (const rootId of rootIds) {
      if (rootId !== snapshot.tree_state.root_node_id) {
        visit(rootId);
      }
    }

    return visible;
  }, [
    rootIds,
    rootNode,
    snapshot.tree_state.root_node_id,
    visibleChildrenById,
  ]);

  const selectedNode = useMemo(() => {
    if (!rootNode) {
      return null;
    }
    const effectiveSelectedId = findVisibleSelectionFallback(
      selectedNodeId,
      visibleNodeIds,
      parentById,
      snapshot.tree_state.root_node_id,
    );
    return (
      nodeById.get(effectiveSelectedId) ??
      nodeById.get(snapshot.tree_state.root_node_id) ??
      null
    );
  }, [
    nodeById,
    parentById,
    rootNode,
    selectedNodeId,
    snapshot.tree_state.root_node_id,
    visibleNodeIds,
  ]);

  useEffect(() => {
    if (!rootNode) {
      return;
    }
    const nextSelectedId =
      selectedNode?.node_id ?? snapshot.tree_state.root_node_id;
    if (nextSelectedId !== selectedNodeId) {
      void onSelectNode(nextSelectedId, false);
    }
  }, [
    onSelectNode,
    rootNode,
    selectedNode?.node_id,
    selectedNodeId,
    snapshot.tree_state.root_node_id,
  ]);

  useEffect(() => {
    if (!focusedNodeId) {
      return;
    }
    if (!nodeById.has(focusedNodeId)) {
      setFocusedNodeId(null);
    }
  }, [focusedNodeId, nodeById]);

  useEffect(() => {
    if (!focusedNodeId || documentsByNode[focusedNodeId]) {
      return;
    }
    void loadNodeDocuments(focusedNodeId).catch(() => undefined);
  }, [documentsByNode, focusedNodeId, loadNodeDocuments]);

  useEffect(() => {
    if (!isFullscreen) {
      return undefined;
    }

    function handleEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setIsFullscreen(false);
      }
    }

    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isFullscreen]);

  const layout = useMemo(
    () => buildTreeLayoutPositions({ nodeById, rootIds, visibleChildrenById }),
    [nodeById, rootIds, visibleChildrenById],
  );

  const flowNodes = useMemo<Node<GraphNodeData>[]>(() => {
    const isSplitBusy = isSplittingNode || Boolean(splittingNodeId);
    return snapshot.tree_state.node_registry
      .filter(
        (node) =>
          node.node_id === snapshot.tree_state.root_node_id ||
          visibleNodeIds.has(node.node_id),
      )
      .map((node) => ({
        id: node.node_id,
        type: "graphNode",
        className: "nopan",
        position: layout.get(node.node_id) ?? { x: node.depth * 350, y: 0 },
        draggable: false,
        selectable: false,
        data: {
          node,
          isCurrent: snapshot.tree_state.active_node_id === node.node_id,
          isSelected: selectedNode?.node_id === node.node_id,
          isCollapsed: collapsedById.get(node.node_id) ?? false,
          directHiddenChildrenCount:
            directHiddenChildrenById.get(node.node_id) ?? 0,
          canCreateChild: node.status !== "done" && !node.is_superseded,
          canFinishTask:
            !node.is_superseded &&
            (activeChildrenById.get(node.node_id) ?? []).length === 0 &&
            (node.status === "ready" || node.status === "in_progress"),
          canSplit: canSplitById.get(node.node_id) ?? false,
          isSplitting: splittingNodeId === node.node_id,
          isSplitDisabled: isSplitBusy,
          onSelect: (nodeId) => {
            void handlerRef.current.onSelectNode(nodeId, true);
          },
          onToggleCollapse: (nodeId) => {
            setCollapseOverrides((current) => {
              const nodeRecord = nodeById.get(nodeId);
              if (!nodeRecord) {
                return current;
              }
              const currentValue =
                typeof current[nodeId] === "boolean"
                  ? current[nodeId]
                  : defaultCollapsedForStatus(nodeRecord.status);
              return { ...current, [nodeId]: !currentValue };
            });
          },
          onCreateChild: (nodeId) => {
            void handlerRef.current.onCreateChild(nodeId);
          },
          onSplit: (nodeId, mode) => {
            void handlerRef.current.onSplitNode(nodeId, mode);
          },
          onOpenBreadcrumb: (nodeId) => {
            void handlerRef.current.onOpenBreadcrumb(nodeId);
          },
          onFinishTask: (nodeId) => {
            void handlerRef.current.onFinishTask(nodeId);
          },
          onInfoClick: (nodeId) => {
            setFocusedNodeId((prev) => (prev === nodeId ? null : nodeId));
            void handlerRef.current.onSelectNode(nodeId, true);
          },
        },
      }));
  }, [
    activeChildrenById,
    canSplitById,
    collapsedById,
    directHiddenChildrenById,
    isSplittingNode,
    layout,
    nodeById,
    selectedNode?.node_id,
    snapshot.tree_state.active_node_id,
    snapshot.tree_state.node_registry,
    snapshot.tree_state.root_node_id,
    splittingNodeId,
    visibleNodeIds,
  ]);

  const flowEdges = useMemo<Edge[]>(() => {
    const visibleSet = new Set(flowNodes.map((node) => node.id));
    return snapshot.tree_state.node_registry.flatMap((node) =>
      (visibleChildrenById.get(node.node_id) ?? [])
        .filter(
          (childId) => visibleSet.has(node.node_id) && visibleSet.has(childId),
        )
        .map((childId) => ({
          id: `e-${node.node_id}-${childId}`,
          source: node.node_id,
          target: childId,
          type: "smoothstep",
          style: { stroke: "var(--color-edge)", strokeWidth: 2.4 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: "var(--color-edge)",
          },
        })),
    );
  }, [flowNodes, snapshot.tree_state.node_registry, visibleChildrenById]);

  const fitKey = useMemo(
    () =>
      flowNodes
        .map(
          (node) =>
            `${node.id}:${node.position.x}:${node.position.y}:${node.data.isCollapsed ? "c" : "o"}`,
        )
        .join("|"),
    [flowNodes],
  );

  useEffect(() => {
    if (!flowInstance || flowNodes.length === 0) {
      return undefined;
    }
    const handle = window.setTimeout(() => {
      flowInstance.fitView({ padding: 0.18, duration: 240, maxZoom: 1.12 });
    }, 20);
    return () => window.clearTimeout(handle);
  }, [fitKey, flowInstance, flowNodes.length, isFullscreen]);

  // XYFlow disables pointer-events for non-selectable, non-draggable nodes unless a node-level
  // interaction handler is provided. Keep a no-op handler so custom node buttons remain clickable
  // without routing selection through the outer wrapper as well as the inner card.
  function handleFlowNodePointerEvents() {
    return undefined;
  }

  return (
    <div
      className={`${styles.graphShell} ${isFullscreen ? styles.graphShellFullscreen : ""}`}
    >
      {hasInvalidRootNode ? (
        <div
          className={styles.invalidState}
          role="alert"
          data-testid="graph-invalid-snapshot"
        >
          <h3>Graph data is invalid</h3>
          <p>
            The project snapshot is missing its root node, so the graph cannot
            be rendered safely.
          </p>
        </div>
      ) : (
        <ReactFlow
          fitView
          proOptions={{ hideAttribution: true }}
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          nodesDraggable={false}
          nodesConnectable={false}
          minZoom={0.2}
          maxZoom={1.35}
          onInit={setFlowInstance}
          onNodeClick={handleFlowNodePointerEvents}
        >
          <Background color="var(--color-border-strong)" gap={24} size={1} />
          <Controls showInteractive={false} />

          <Panel position="bottom-left">
            <button
              type="button"
              className={styles.fullscreenButton}
              onClick={() => setIsFullscreen((current) => !current)}
            >
              {isFullscreen ? "Exit Fullscreen" : "Fullscreen"}
            </button>
          </Panel>

          {focusedNodeId ? (
            <Panel position="top-right" className={styles.detailPanel}>
              <div className={styles.detailCard}>
                <div className={styles.detailCardHeader}>
                  <span className={styles.detailCardTitle}>Node Detail</span>
                  <button
                    type="button"
                    className={styles.detailCardClose}
                    onClick={() => setFocusedNodeId(null)}
                    aria-label="Close detail panel"
                    title="Close"
                  >
                    ×
                  </button>
                </div>
                {(() => {
                  const focusedNode = nodeById.get(focusedNodeId) ?? null;
                  if (!focusedNode) return null;
                  return (
                    <TaskPanel
                      node={focusedNode}
                      documents={documentsByNode[focusedNode.node_id]}
                      isLoading={isLoadingDocuments}
                      isUpdating={isUpdatingDocument}
                      isConfirming={isConfirmingNode}
                      compact
                      activity={agentActivityByNode[focusedNode.node_id]}
                      onReload={() =>
                        loadNodeDocuments(focusedNode.node_id).then(
                          () => undefined,
                        )
                      }
                      onSave={(payload) =>
                        updateNodeTask(focusedNode.node_id, payload)
                      }
                      onConfirm={() => confirmTask(focusedNode.node_id)}
                      onRetryBrief={() => confirmTask(focusedNode.node_id)}
                    />
                  );
                })()}
              </div>
            </Panel>
          ) : null}
        </ReactFlow>
      )}
    </div>
  );
}
