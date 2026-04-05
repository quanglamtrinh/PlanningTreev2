import { fireEvent, render, screen, within } from '@testing-library/react'
import { useEffect, type ComponentType, type ReactNode } from 'react'
import { MemoryRouter } from 'react-router-dom'
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
  const onCreateTask = vi.fn(async () => 'child-created')
  const onSplitNode = vi.fn(async () => undefined)
  const onOpenBreadcrumb = vi.fn(async () => undefined)
  const onResetProject = vi.fn(async () => undefined)
  const view = render(
    <MemoryRouter>
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
        onCreateTask={onCreateTask}
        onSplitNode={onSplitNode}
        onOpenBreadcrumb={onOpenBreadcrumb}
        onResetProject={onResetProject}
      />
    </MemoryRouter>,
  )
  return {
    ...view,
    onCreateChild,
    onCreateTask,
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

  it('shows execution lifecycle badge separately from the coarse node status', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({
            node_id: 'root',
            status: 'in_progress',
            workflow: {
              frame_confirmed: true,
              active_step: 'spec',
              spec_confirmed: true,
              execution_status: 'completed',
            },
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    const graphNode = screen.getByTestId('graph-node-root')
    expect(within(graphNode).getByText('In Progress')).toBeInTheDocument()
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
    expect(screen.queryByText('Finish Task')).not.toBeInTheDocument()
    expect(screen.getByText('AI Split')).toBeInTheDocument()
    expect(screen.getByText('Workflow')).toBeInTheDocument()
    expect(screen.getByText('Phase Breakdown')).toBeInTheDocument()
  })

  it('keeps Open Breadcrumb enabled even when Codex CLI is unavailable', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [buildNode({ node_id: 'root', child_ids: [] })],
      },
    })

    renderTreeGraph(snapshot, { codexAvailable: false })

    const rootWrapper = screen.getByTestId('rf-node-root')
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Node actions' }))
    expect(screen.getByText('Open Breadcrumb').closest('button')).toBeEnabled()
  })

  it('renders init-node actions only when the node is marked as init', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({
            node_id: 'root',
            child_ids: [],
            is_init_node: true,
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    const rootWrapper = screen.getByTestId('rf-node-root')
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Node actions' }))

    expect(screen.getByText('Init Docs For Project')).toBeInTheDocument()
    expect(screen.getByText('Create A Task')).toBeInTheDocument()
    expect(screen.queryByText('Open Breadcrumb')).not.toBeInTheDocument()
    expect(screen.queryByText('AI Split')).not.toBeInTheDocument()
  })

  it('opens breadcrumb from the action menu for a done node', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'root',
        node_registry: [
          buildNode({
            node_id: 'root',
            status: 'done',
            child_ids: [],
          }),
        ],
      },
    })

    const { onOpenBreadcrumb } = renderTreeGraph(snapshot)

    const rootWrapper = screen.getByTestId('rf-node-root')
    fireEvent.click(within(rootWrapper).getByRole('button', { name: 'Node actions' }))
    fireEvent.click(screen.getByText('Open Breadcrumb'))

    expect(onOpenBreadcrumb).toHaveBeenCalledWith('root')
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

  it('enables Split when workflow readiness is met', () => {
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
    expect(screen.getByText('Workflow').closest('button')).toBeEnabled()
  })

  it('graph node details shows info (describe) only — no workflow stepper or document tabs', async () => {
    const snapshot = buildSnapshot()

    renderTreeGraph(snapshot)
    fireEvent.click(screen.getByRole('button', { name: 'Node details' }))
    const detailCard = screen.getByTestId('graph-node-detail-card')

    expect(within(detailCard).queryByTestId('workflow-stepper')).not.toBeInTheDocument()
    expect(within(detailCard).queryByRole('tablist', { name: 'Task document sections' })).not.toBeInTheDocument()
    expect(within(detailCard).getByText('Root node')).toBeInTheDocument()
    expect(within(detailCard).queryByRole('button', { name: 'Open Breadcrumb' })).not.toBeInTheDocument()
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

  it('renders a real review overlay and ghost siblings from sibling_manifest on lazy trees', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'child-1',
        node_registry: [
          buildNode({
            node_id: 'root',
            child_ids: ['child-1'],
            review_node_id: 'review-1',
          }),
          buildNode({
            node_id: 'child-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Prep',
            description: 'First lazy step',
            depth: 1,
            display_order: 0,
            hierarchical_number: '1.1',
            status: 'ready',
            node_kind: 'original',
          }),
          buildNode({
            node_id: 'review-1',
            parent_id: 'root',
            child_ids: [],
            title: 'Review',
            description: 'Review node',
            depth: 1,
            display_order: 99,
            hierarchical_number: '1.R',
            status: 'ready',
            node_kind: 'review',
            workflow: null,
            review_summary: {
              checkpoint_count: 1,
              rollup_status: 'pending',
              pending_sibling_count: 2,
              pending_siblings: [
                { index: 2, title: 'Build', materialized_node_id: null },
                { index: 3, title: 'Polish', materialized_node_id: null },
              ],
              sibling_manifest: [
                {
                  index: 1,
                  title: 'Prep',
                  objective: 'First lazy step',
                  materialized_node_id: 'child-1',
                  status: 'active',
                  checkpoint_label: null,
                },
                {
                  index: 2,
                  title: 'Build',
                  objective: 'Second lazy step',
                  materialized_node_id: null,
                  status: 'pending',
                  checkpoint_label: null,
                },
                {
                  index: 3,
                  title: 'Polish',
                  objective: 'Final lazy step',
                  materialized_node_id: null,
                  status: 'pending',
                  checkpoint_label: null,
                },
              ],
            },
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    expect(screen.getByTestId('rf-node-review-1')).toBeInTheDocument()
    expect(screen.queryByTestId('rf-node-review::root')).not.toBeInTheDocument()

    const reviewCard = screen.getByTestId('graph-review-node-root')
    expect(within(reviewCard).getByText('1.A')).toBeInTheDocument()
    expect(within(reviewCard).getByText('1.B')).toBeInTheDocument()
    expect(within(reviewCard).getByText('1.C')).toBeInTheDocument()

    const ghostB = screen.getByTestId('graph-ghost-node-2')
    expect(within(ghostB).getByText('1.B')).toBeInTheDocument()
    expect(within(ghostB).getByText('Second lazy step')).toBeInTheDocument()

    const ghostC = screen.getByTestId('graph-ghost-node-3')
    expect(within(ghostC).getByText('1.C')).toBeInTheDocument()
    expect(within(ghostC).getByText('Final lazy step')).toBeInTheDocument()

    expect(renderedEdges('ghost-review')).toHaveLength(2)
    expect(screen.getByTestId('rf-edge-ghost-review-ghost::root::2')).toHaveAttribute(
      'data-edge-target',
      'review-1',
    )
    expect(screen.getByTestId('rf-edge-ghost-review-ghost::root::3')).toHaveAttribute(
      'data-edge-target',
      'review-1',
    )
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
