import { fireEvent, render, screen, within } from '@testing-library/react'
import { useEffect, type ComponentType, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { apiMock } = vi.hoisted(() => ({
  apiMock: {
    getNodeDocument: vi.fn(),
    putNodeDocument: vi.fn(),
    getDetailState: vi.fn().mockResolvedValue({
      node_id: 'root',
      frame_confirmed: false,
      frame_confirmed_revision: 0,
      frame_revision: 0,
      active_step: 'frame' as const,
      workflow_notice: null,
      frame_needs_reconfirm: false,
      frame_read_only: false,
      clarify_read_only: true,
      clarify_confirmed: false,
      spec_read_only: true,
      spec_stale: false,
      spec_confirmed: false,
    }),
    getSnapshot: vi.fn(),
    confirmFrame: vi.fn(),
    getClarify: vi.fn().mockResolvedValue({
      schema_version: 2,
      source_frame_revision: 0,
      confirmed_revision: 0,
      confirmed_at: null,
      questions: [
        {
          field_name: 'target_platform',
          question: 'What target platform?',
          why_it_matters: '',
          current_value: '',
          options: [],
          selected_option_id: null,
          custom_answer: '',
          allow_custom: true,
        },
      ],
      updated_at: null,
    }),
    updateClarify: vi.fn(),
    confirmClarify: vi.fn(),
    confirmSpec: vi.fn(),
    generateFrame: vi.fn(),
    getFrameGenStatus: vi.fn(),
    generateClarify: vi.fn(),
    getClarifyGenStatus: vi.fn(),
    generateSpec: vi.fn(),
    getSpecGenStatus: vi.fn().mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    }),
  },
}))

vi.mock('@xyflow/react', () => ({
  useStore: (selector: (state: { transform: [number, number, number] }) => unknown) =>
    selector({ transform: [0, 0, 1] }),
  ReactFlow: ({
    nodes,
    edges,
    nodeTypes,
    children,
    onInit,
    onNodeClick,
  }: {
    nodes: Array<{
      id: string
      type: string
      data: unknown
      className?: string
      position?: { x: number; y: number }
    }>
    edges?: Array<{
      id: string
      source: string
      target: string
      data?: { kind?: string }
      sourcePosition?: string
      targetPosition?: string
      markerEnd?: unknown
      style?: { strokeDasharray?: string | number }
    }>
    nodeTypes: Record<string, ComponentType<Record<string, unknown>>>
    children?: ReactNode
    onInit?: (instance: { fitView: ReturnType<typeof vi.fn> }) => void
    onNodeClick?: (event: unknown, node: { id: string }) => void
  }) => {
    useEffect(() => {
      onInit?.({ fitView: vi.fn() })
    }, [onInit])

    return (
      <div
        data-testid="mock-reactflow"
        data-has-node-click={String(Boolean(onNodeClick))}
      >
        {(edges ?? []).map((edge) => (
          <div
            key={edge.id}
            data-testid={`rf-edge-${edge.id}`}
            data-edge-kind={edge.data?.kind ?? ''}
            data-edge-source={edge.source}
            data-edge-target={edge.target}
            data-edge-source-position={edge.sourcePosition ?? ''}
            data-edge-target-position={edge.targetPosition ?? ''}
            data-edge-dashed={String(Boolean(edge.style?.strokeDasharray))}
            data-edge-has-marker={String(Boolean(edge.markerEnd))}
          />
        ))}
        {nodes.map((node) => {
          const NodeComponent = nodeTypes[node.type]
          return (
            <div
              key={node.id}
              data-testid={`rf-node-${node.id}`}
              data-position-x={String(node.position?.x ?? '')}
              data-position-y={String(node.position?.y ?? '')}
              className={node.className}
              onClick={() => onNodeClick?.({}, { id: node.id })}
            >
              <NodeComponent
                id={node.id}
                data={node.data}
                selected={false}
                dragging={false}
                xPos={0}
                yPos={0}
                zIndex={0}
                isConnectable={false}
                type={node.type}
              />
            </div>
          )
        })}
        {children}
      </div>
    )
  },
  Background: () => null,
  Controls: () => null,
  MarkerType: { ArrowClosed: 'arrowclosed' },
  Panel: ({ children, className }: { children?: ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
  Handle: () => null,
  Position: { Left: 'left', Right: 'right', Top: 'top', Bottom: 'bottom' },
}))

vi.mock('@uiw/react-codemirror', () => ({
  default: ({
    value,
    onChange,
    onBlur,
  }: {
    value: string
    onChange?: (value: string) => void
    onBlur?: () => void
  }) => (
    <textarea
      data-testid="mock-codemirror"
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      onBlur={() => onBlur?.()}
    />
  ),
}))

vi.mock('../../src/api/client', () => ({
  api: apiMock,
  ApiError: class extends Error {
    status: number
    code: string | null
    constructor(status = 400, payload: { message?: string; code?: string } | null = null) {
      super(payload?.message ?? 'Request failed')
      this.status = status
      this.code = payload?.code ?? null
    }
  },
}))

import type { NodeRecord, Snapshot } from '../../src/api/types'
import { TreeGraph } from '../../src/features/graph/TreeGraph'
import {
  estimateNodeHeight,
  GRAPH_NODE_MARGIN_BOTTOM_PX,
} from '../../src/features/graph/treeGraphLayout'
import { useNodeDocumentStore } from '../../src/stores/node-document-store'
import { useDetailStateStore } from '../../src/stores/detail-state-store'
import { useClarifyStore } from '../../src/stores/clarify-store'
import { useProjectStore } from '../../src/stores/project-store'

function buildNode(overrides: Partial<NodeRecord>): NodeRecord {
  return {
    node_id: 'root',
    parent_id: null,
    child_ids: [],
    title: 'Root',
    description: 'Root node',
    status: 'draft',
    node_kind: 'root',
    depth: 0,
    display_order: 0,
    hierarchical_number: '1',
    is_superseded: false,
    created_at: '2026-03-20T00:00:00Z',
    workflow: {
      frame_confirmed: false,
      active_step: 'frame',
      spec_confirmed: false,
    },
    ...overrides,
  }
}

function buildSnapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    schema_version: 6,
    project: {
      id: 'project-1',
      name: 'Alpha',
      root_goal: 'Ship graph-only reset',
      project_path: 'C:/workspace/alpha',
      created_at: '2026-03-20T00:00:00Z',
      updated_at: '2026-03-20T00:00:00Z',
    },
    tree_state: {
      root_node_id: 'root',
      active_node_id: 'root',
      node_registry: [buildNode({})],
    },
    updated_at: '2026-03-20T00:00:00Z',
    ...overrides,
  }
}

function renderTreeGraph(
  snapshot: Snapshot,
  options: {
    onSelectNode?: ReturnType<typeof vi.fn>
    selectedNodeId?: string | null
    codexAvailable?: boolean
  } = {},
) {
  const onSelectNode = options.onSelectNode ?? vi.fn(async () => undefined)
  const onCreateChild = vi.fn(async () => undefined)
  const onSplitNode = vi.fn(async () => undefined)
  const onOpenBreadcrumb = vi.fn(async () => undefined)
  const onFinishTask = vi.fn(async () => undefined)
  const onResetProject = vi.fn(async () => undefined)
  const view = render(
    <TreeGraph
      snapshot={snapshot}
      selectedNodeId={options.selectedNodeId ?? snapshot.tree_state.active_node_id}
      splitStatus="idle"
      splittingNodeId={null}
      isCreatingNode={false}
      isResettingProject={false}
      isResetDisabled={false}
      codexAvailable={options.codexAvailable ?? true}
      onSelectNode={onSelectNode}
      onCreateChild={onCreateChild}
      onSplitNode={onSplitNode}
      onOpenBreadcrumb={onOpenBreadcrumb}
      onFinishTask={onFinishTask}
      onResetProject={onResetProject}
    />,
  )
  return {
    ...view,
    onCreateChild,
    onFinishTask,
    onOpenBreadcrumb,
    onResetProject,
    onSelectNode,
    onSplitNode,
  }
}

function renderedEdges(kind?: string): HTMLElement[] {
  const allEdges = screen.queryAllByTestId(/^rf-edge-/)
  if (!kind) {
    return allEdges
  }
  return allEdges.filter((edge) => edge.getAttribute('data-edge-kind') === kind)
}

describe('TreeGraph', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
    useNodeDocumentStore.getState().reset()
    useDetailStateStore.getState().reset()
    useClarifyStore.getState().reset()
    apiMock.getNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-20T00:00:00Z',
    })
    apiMock.putNodeDocument.mockResolvedValue({
      node_id: 'root',
      kind: 'frame',
      content: '# Frame',
      updated_at: '2026-03-20T00:00:00Z',
    })
    apiMock.getFrameGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
    apiMock.getClarifyGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
    apiMock.getSpecGenStatus.mockResolvedValue({
      status: 'idle',
      job_id: null,
      started_at: null,
      completed_at: null,
      error: null,
    })
  })

  it('always includes the root node in the ReactFlow node set', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({ node_id: 'root', child_ids: ['child-1'] }),
          buildNode({
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Child',
            description: 'Child node',
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            status: 'ready',
            node_kind: 'original',
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    expect(screen.getByTestId('rf-node-root')).toBeInTheDocument()
    expect(screen.getByTestId('graph-node-root')).toBeInTheDocument()
  })

  it('expands a locked parent to reveal children via the collapse toggle', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({ node_id: 'root', child_ids: ['child-1'], status: 'locked' }),
          buildNode({
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Child',
            description: 'Child node',
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            status: 'ready',
            node_kind: 'original',
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    expect(screen.queryByTestId('rf-node-child-1')).not.toBeInTheDocument()
    const rootWrapper = screen.getByTestId('rf-node-root')
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Expand node' }))
    expect(screen.getByTestId('rf-node-child-1')).toBeInTheDocument()
  })

  it('keeps node wrappers interactive and exposes split actions', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [buildNode({ node_id: 'root', child_ids: ['child-1'] })],
      },
    })

    renderTreeGraph(snapshot)

    const reactFlow = screen.getByTestId('mock-reactflow')
    const rootWrapper = screen.getByTestId('rf-node-root')
    const rootNode = screen.getByTestId('graph-node-root')

    expect(reactFlow).toHaveAttribute('data-has-node-click', 'true')
    expect(rootWrapper).toHaveClass('nopan')
    expect(rootNode).toHaveClass('nodrag', 'nopan')
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Node actions' }))
    expect(screen.getByText('Create Child')).toBeInTheDocument()
    expect(screen.getByText('Open Breadcrumb')).toBeInTheDocument()
    expect(screen.getByText('AI Split')).toBeInTheDocument()
    expect(screen.getByText('Workflow')).toBeInTheDocument()
    expect(screen.getByText('Phase Breakdown')).toBeInTheDocument()
  })

  it('disables Finish Task until spec is confirmed', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({
            node_id: 'root',
            status: 'ready',
            workflow: {
              frame_confirmed: true,
              active_step: 'spec',
              spec_confirmed: false,
            },
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    const rootWrapper = screen.getByTestId('rf-node-root')
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Node actions' }))
    expect(screen.getByText('Finish Task').closest('button')).toBeDisabled()
  })

  it('disables Split until the node reaches the Spec workflow step', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({
            node_id: 'root',
            status: 'ready',
            workflow: {
              frame_confirmed: true,
              active_step: 'clarify',
              spec_confirmed: false,
            },
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    const rootWrapper = screen.getByTestId('rf-node-root')
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Node actions' }))
    expect(screen.getByText('Workflow').closest('button')).toBeDisabled()
  })

  it('enables Finish Task and Split only when workflow readiness is met', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({
            node_id: 'root',
            status: 'ready',
            workflow: {
              frame_confirmed: true,
              active_step: 'spec',
              spec_confirmed: true,
            },
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    const rootWrapper = screen.getByTestId('rf-node-root')
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Node actions' }))
    expect(screen.getByText('Finish Task').closest('button')).toBeEnabled()
    expect(screen.getByText('Workflow').closest('button')).toBeEnabled()
  })

  it('shows Describe -> Frame -> Clarify -> Spec stepper in the detail panel header', async () => {
    const snapshot = buildSnapshot()

    renderTreeGraph(snapshot)
    fireEvent.click(screen.getByRole('button', { name: 'Node details' }))
    const detailCard = screen.getByTestId('graph-node-detail-card')

    expect(within(detailCard).getByRole('button', { name: 'Describe' })).toBeInTheDocument()
    expect(within(detailCard).getByRole('button', { name: 'Frame' })).toBeInTheDocument()
    expect(await within(detailCard).findByRole('button', { name: 'Clarify' })).toBeInTheDocument()
    expect(within(detailCard).getByRole('button', { name: 'Spec' })).toBeInTheDocument()
    fireEvent.click(within(detailCard).getByRole('button', { name: 'Describe' }))
    expect(within(detailCard).getByText('Root node')).toBeInTheDocument()
    expect(within(detailCard).queryByRole('button', { name: 'Open Breadcrumb' })).not.toBeInTheDocument()
    expect(within(detailCard).queryByRole('button', { name: 'Finish Task' })).not.toBeInTheDocument()

    fireEvent.click(within(detailCard).getByRole('button', { name: 'Clarify' }))
    expect(await within(detailCard).findByText(/What target platform/)).toBeInTheDocument()

    apiMock.getNodeDocument.mockResolvedValueOnce({
      node_id: 'root',
      kind: 'spec',
      content: '# Spec',
      updated_at: '2026-03-20T00:00:01Z',
    })
    fireEvent.click(within(detailCard).getByRole('button', { name: 'Spec' }))
    expect(await within(detailCard).findByDisplayValue('# Spec')).toBeInTheDocument()
  })

  it('renders child-to-review arrows and a review-return arrow while keeping structural edges', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({ node_id: 'root', child_ids: ['child-1', 'child-2', 'child-3'] }),
          buildNode({
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Prep',
            description: 'Prep step',
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            status: 'ready',
            node_kind: 'original',
          }),
          buildNode({
            node_id: 'child-2',
            parent_id: 'root',
            child_ids: [],
            title: 'Build',
            description: 'Build step',
            depth: 1,
            display_order: 1,
            hierarchical_number: '1.2',
            status: 'locked',
            node_kind: 'original',
          }),
          buildNode({
            node_id: 'child-3',
            parent_id: 'root',
            child_ids: [],
            title: 'Polish',
            description: 'Polish step',
            depth: 1,
            display_order: 2,
            hierarchical_number: '1.3',
            status: 'locked',
            node_kind: 'original',
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    expect(screen.getByTestId('rf-node-review::root')).toBeInTheDocument()
    expect(screen.getByTestId('graph-review-node-root')).toHaveTextContent('Review')
    expect(renderedEdges('structural')).toHaveLength(3)
    expect(renderedEdges('review-child')).toHaveLength(3)
    expect(renderedEdges('review-return')).toHaveLength(1)
    expect(screen.getByTestId('rf-edge-review-child-child-1-root')).toHaveAttribute('data-edge-source', 'child-1')
    expect(screen.getByTestId('rf-edge-review-child-child-1-root')).toHaveAttribute('data-edge-target', 'review::root')
    expect(screen.getByTestId('rf-edge-review-child-child-1-root')).toHaveAttribute('data-edge-source-position', 'top')
    expect(screen.getByTestId('rf-edge-review-child-child-1-root')).toHaveAttribute('data-edge-target-position', 'bottom')
    expect(screen.getByTestId('rf-edge-review-child-child-1-root')).toHaveAttribute('data-edge-dashed', 'false')
    expect(screen.getByTestId('rf-edge-review-child-child-2-root')).toHaveAttribute('data-edge-source-position', 'top')
    expect(screen.getByTestId('rf-edge-review-child-child-3-root')).toHaveAttribute('data-edge-source-position', 'top')
    expect(screen.getByTestId('rf-edge-review-return-root')).toHaveAttribute('data-edge-source', 'review::root')
    expect(screen.getByTestId('rf-edge-review-return-root')).toHaveAttribute('data-edge-target', 'root')
    expect(screen.getByTestId('rf-edge-review-return-root')).toHaveAttribute('data-edge-source-position', 'top')
    expect(screen.getByTestId('rf-edge-review-return-root')).toHaveAttribute('data-edge-target-position', 'bottom')
    expect(screen.getByTestId('rf-edge-review-return-root')).toHaveAttribute('data-edge-has-marker', 'true')
    expect(screen.getByTestId('rf-edge-review-return-root')).toHaveAttribute('data-edge-dashed', 'false')
    expect(screen.getByTestId('rf-edge-e-root-child-1')).toHaveAttribute('data-edge-kind', 'structural')
  })

  it('does not render a review overlay for parents with fewer than two active children', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({ node_id: 'root', child_ids: ['child-1'] }),
          buildNode({
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Only child',
            description: 'Single visible child',
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            status: 'ready',
            node_kind: 'original',
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    expect(screen.queryByTestId('rf-node-review::root')).not.toBeInTheDocument()
    expect(renderedEdges('structural')).toHaveLength(1)
    expect(renderedEdges('review-child')).toHaveLength(0)
    expect(renderedEdges('review-return')).toHaveLength(0)
  })

  it('removes the review overlay when a branch is collapsed', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({
            node_id: 'root',
            child_ids: ['child-1', 'child-2', 'child-3'],
            status: 'locked',
          }),
          buildNode({
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Prep',
            description: 'Prep step',
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            status: 'ready',
            node_kind: 'original',
          }),
          buildNode({
            node_id: 'child-2',
            parent_id: 'root',
            child_ids: [],
            title: 'Build',
            description: 'Build step',
            depth: 1,
            display_order: 1,
            hierarchical_number: '1.2',
            status: 'locked',
            node_kind: 'original',
          }),
          buildNode({
            node_id: 'child-3',
            parent_id: 'root',
            child_ids: [],
            title: 'Polish',
            description: 'Polish step',
            depth: 1,
            display_order: 2,
            hierarchical_number: '1.3',
            status: 'locked',
            node_kind: 'original',
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    expect(screen.queryByTestId('rf-node-review::root')).not.toBeInTheDocument()
    const rootWrapper = screen.getByTestId('rf-node-root')
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Expand node' }))
    expect(screen.getByTestId('rf-node-review::root')).toBeInTheDocument()
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Collapse node' }))
    expect(screen.queryByTestId('rf-node-review::root')).not.toBeInTheDocument()
  })

  it('does not render a review overlay when the parent is outside the current graph root', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({ node_id: 'root', child_ids: ['child-1', 'child-2'] }),
          buildNode({
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Prep',
            description: 'Prep step',
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            status: 'ready',
            node_kind: 'original',
          }),
          buildNode({
            node_id: 'child-2',
            parent_id: 'root',
            child_ids: [],
            title: 'Build',
            description: 'Build step',
            depth: 1,
            display_order: 1,
            hierarchical_number: '1.2',
            status: 'ready',
            node_kind: 'original',
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    expect(screen.getByTestId('rf-node-review::root')).toBeInTheDocument()
    const childWrapper = screen.getByTestId('rf-node-child-1')
    fireEvent.click(within(childWrapper).getByRole('button', { name: 'Node actions' }))
    fireEvent.click(screen.getByRole('button', { name: /Set as current root/i }))

    expect(screen.queryByTestId('rf-node-root')).not.toBeInTheDocument()
    expect(screen.queryByTestId('rf-node-review::root')).not.toBeInTheDocument()
  })

  it('keeps the review card read-only and clicking it does not select a node', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({ node_id: 'root', child_ids: ['child-1', 'child-2'] }),
          buildNode({
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Prep',
            description: 'Prep step',
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            status: 'ready',
            node_kind: 'original',
          }),
          buildNode({
            node_id: 'child-2',
            parent_id: 'root',
            child_ids: [],
            title: 'Build',
            description: 'Build step',
            depth: 1,
            display_order: 1,
            hierarchical_number: '1.2',
            status: 'locked',
            node_kind: 'original',
          }),
        ],
      },
    })

    const onSelectNode = vi.fn(async () => undefined)
    renderTreeGraph(snapshot, { onSelectNode })

    const reviewCard = screen.getByTestId('graph-review-node-root')
    fireEvent.click(reviewCard)

    expect(onSelectNode).not.toHaveBeenCalled()
    expect(within(reviewCard).queryByRole('button')).not.toBeInTheDocument()
  })

  it('places the review node between the parent row and the direct child row', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({ node_id: 'root', child_ids: ['child-1', 'child-2'] }),
          buildNode({
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: ['grandchild-1'],
            title: 'Prep',
            description: 'Prep step',
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            status: 'ready',
            node_kind: 'original',
          }),
          buildNode({
            node_id: 'child-2',
            parent_id: 'root',
            child_ids: [],
            title: 'Build',
            description: 'Build step',
            depth: 1,
            display_order: 1,
            hierarchical_number: '1.2',
            status: 'locked',
            node_kind: 'original',
          }),
          buildNode({
            node_id: 'grandchild-1',
            parent_id: 'child-1',
            child_ids: [],
            title: 'Prep detail',
            description: 'Grandchild step',
            depth: 2,
            display_order: 0,
            hierarchical_number: '1.1.1',
            status: 'ready',
            node_kind: 'original',
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    const parentNode = screen.getByTestId('rf-node-root')
    const directChildNode = screen.getByTestId('rf-node-child-1')
    const reviewNode = screen.getByTestId('rf-node-review::root')
    const grandchildNode = screen.getByTestId('rf-node-grandchild-1')
    const parentY = Number(parentNode.getAttribute('data-position-y'))
    const directChildY = Number(directChildNode.getAttribute('data-position-y'))
    const reviewY = Number(reviewNode.getAttribute('data-position-y'))
    const grandchildY = Number(grandchildNode.getAttribute('data-position-y'))

    const parentRecord = snapshot.tree_state.node_registry.find((n) => n.node_id === 'root')
    expect(parentRecord).toBeDefined()
    const parentBottom = parentY + estimateNodeHeight(parentRecord!) + GRAPH_NODE_MARGIN_BOTTOM_PX
    // Review is centered between parent bottom and the children row.
    expect(reviewY).toBeGreaterThan(parentBottom)
    expect(reviewY).toBeLessThan(directChildY)
    expect(reviewY).toBeGreaterThan(parentY)
    expect(grandchildY).toBeGreaterThan(directChildY)
  })
})
