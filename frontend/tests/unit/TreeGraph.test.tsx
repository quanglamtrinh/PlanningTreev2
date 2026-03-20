import { fireEvent, render, screen, within } from '@testing-library/react'
import { useEffect, type ComponentType, type ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { layoutSpy } = vi.hoisted(() => ({
  layoutSpy: vi.fn(),
}))

vi.mock('@xyflow/react', () => ({
  ReactFlow: ({
    nodes,
    nodeTypes,
    children,
    onInit,
    onNodeClick,
  }: {
    nodes: Array<{ id: string; type: string; data: unknown; className?: string }>
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
        {nodes.map((node) => {
          const NodeComponent = nodeTypes[node.type]
          return (
            <div
              key={node.id}
              data-testid={`rf-node-${node.id}`}
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
  Panel: ({ children, className }: { children?: ReactNode; className?: string }) => (
    <div className={className}>{children}</div>
  ),
  Handle: () => null,
  Position: { Left: 'left', Right: 'right' },
  MarkerType: { ArrowClosed: 'arrow-closed' },
}))

vi.mock('../../src/features/graph/treeGraphLayout', async () => {
  const actual = await vi.importActual<typeof import('../../src/features/graph/treeGraphLayout')>(
    '../../src/features/graph/treeGraphLayout',
  )
  return {
    ...actual,
    buildTreeLayoutPositions: vi.fn((args) => {
      layoutSpy()
      return actual.buildTreeLayoutPositions(args)
    }),
  }
})

import type { NodeRecord, Snapshot } from '../../src/api/types'
import { TreeGraph } from '../../src/features/graph/TreeGraph'
import { useProjectStore } from '../../src/stores/project-store'

function buildNode(overrides: Partial<NodeRecord>): NodeRecord {
  return {
    node_id: 'root',
    parent_id: null,
    child_ids: [],
    title: 'Root',
    description: 'Root node',
    status: 'draft',
    phase: 'planning',
    node_kind: 'original',
    planning_mode: null,
    depth: 0,
    display_order: 0,
    hierarchical_number: '1',
    split_metadata: null,
    chat_session_id: null,
    has_planning_thread: false,
    has_execution_thread: false,
    planning_thread_status: null,
    execution_thread_status: null,
    has_ask_thread: false,
    ask_thread_status: null,
    is_superseded: false,
    created_at: '2026-03-08T00:00:00Z',
    ...overrides,
  }
}

function buildSnapshot(overrides: Partial<Snapshot> = {}): Snapshot {
  return {
    schema_version: 2,
    project: {
      id: 'project-1',
      name: 'Alpha',
      root_goal: 'Ship phase 3',
      base_workspace_root: 'C:/workspace',
      project_workspace_root: 'C:/workspace/alpha',
      created_at: '2026-03-08T00:00:00Z',
      updated_at: '2026-03-08T00:00:00Z',
    },
    tree_state: {
      root_node_id: 'root',
      active_node_id: 'root',
      node_registry: [buildNode({})],
    },
    updated_at: '2026-03-08T00:00:00Z',
    ...overrides,
  }
}

function renderTreeGraph(
  snapshot: Snapshot,
  options: {
    isSplittingNode?: boolean
    isResetDisabled?: boolean
    isResettingProject?: boolean
  } = {},
) {
  const onSplitNode = vi.fn(async () => undefined)
  const onFinishTask = vi.fn(async () => undefined)
  const onResetProject = vi.fn(async () => undefined)
  const view = render(
    <TreeGraph
      snapshot={snapshot}
      selectedNodeId={snapshot.tree_state.active_node_id}
      isCreatingNode={false}
      isSplittingNode={options.isSplittingNode ?? false}
      isResettingProject={options.isResettingProject ?? false}
      isResetDisabled={options.isResetDisabled ?? false}
      splittingNodeId={options.isSplittingNode ? snapshot.tree_state.root_node_id : null}
      onSelectNode={vi.fn(async () => undefined)}
      onCreateChild={vi.fn(async () => undefined)}
      onSplitNode={onSplitNode}
      onOpenBreadcrumb={vi.fn(async () => undefined)}
      onFinishTask={onFinishTask}
      onResetProject={onResetProject}
    />,
  )
  return { ...view, onSplitNode, onFinishTask, onResetProject }
}

describe('TreeGraph', () => {
  beforeEach(() => {
    layoutSpy.mockClear()
    useProjectStore.setState(useProjectStore.getInitialState())
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
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    expect(screen.getByTestId('rf-node-root')).toBeInTheDocument()
    expect(screen.getByTestId('graph-node-root')).toBeInTheDocument()
  })

  it('keeps node wrappers interactive without letting the pane capture graph controls', () => {
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
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    const reactFlow = screen.getByTestId('mock-reactflow')
    const rootWrapper = screen.getByTestId('rf-node-root')
    const rootNode = screen.getByTestId('graph-node-root')

    expect(reactFlow).toHaveAttribute('data-has-node-click', 'true')
    expect(rootWrapper).toHaveClass('nopan')
    expect(rootNode).toHaveClass('nodrag', 'nopan')
    expect(within(rootNode).getByRole('button', { name: 'Collapse node' })).toHaveClass('nodrag', 'nopan')
    expect(within(rootNode).getByRole('button', { name: 'Node details' })).toHaveClass('nodrag', 'nopan')
    expect(within(rootWrapper).getByRole('button', { name: 'Node actions' })).toHaveClass('nodrag', 'nopan')
  })

  it('keeps the root node visible when descendants are collapsed', () => {
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
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    fireEvent.click(
      within(screen.getByTestId('graph-node-root')).getByRole('button', { name: 'Collapse node' }),
    )

    expect(screen.getByTestId('graph-node-root')).toBeInTheDocument()
    expect(screen.queryByTestId('graph-node-child-1')).not.toBeInTheDocument()
  })

  it('shows an explicit error state when the snapshot root node is missing', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'missing-root',
        active_node_id: 'missing-root',
        node_registry: [
          buildNode({
            node_id: 'other-node',
            title: 'Other',
            hierarchical_number: '9',
          }),
        ],
      },
    })

    renderTreeGraph(snapshot)

    expect(screen.getByTestId('graph-invalid-snapshot')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Graph data is invalid')
    expect(screen.queryByTestId('mock-reactflow')).not.toBeInTheDocument()
  })

  it('renders reset below fullscreen and wires it to the project reset handler', () => {
    const { onResetProject } = renderTreeGraph(buildSnapshot())

    const fullscreenButton = screen.getByRole('button', { name: 'Fullscreen' })
    const resetButton = screen.getByRole('button', { name: 'Reset to Root' })
    const controlStack = fullscreenButton.parentElement

    expect(controlStack).not.toBeNull()
    expect(within(controlStack as HTMLElement).getAllByRole('button').map((button) => button.textContent)).toEqual([
      'Fullscreen',
      'Reset to Root',
    ])

    fireEvent.click(resetButton)

    expect(onResetProject).toHaveBeenCalledTimes(1)
  })

  it('disables the reset control while a split is running', () => {
    renderTreeGraph(buildSnapshot(), { isResetDisabled: true, isSplittingNode: true })

    expect(screen.getByRole('button', { name: 'Reset to Root' })).toBeDisabled()
  })

  it('wires split actions through the node menu when the node can split', () => {
    const { onSplitNode } = renderTreeGraph(buildSnapshot())

    fireEvent.click(
      within(screen.getByTestId('rf-node-root')).getByRole('button', { name: 'Node actions' }),
    )

    const aiPlanningSection = screen.getByText('AI Planning').closest('div')
    expect(aiPlanningSection).not.toBeNull()
    const workflow = within(aiPlanningSection as HTMLElement).getByText('Workflow').closest('button')
    const simplifyWorkflow = within(aiPlanningSection as HTMLElement)
      .getByText('Simplify Workflow')
      .closest('button')
    const phaseBreakdown = within(aiPlanningSection as HTMLElement)
      .getByText('Phase Breakdown')
      .closest('button')
    const agentBreakdown = within(aiPlanningSection as HTMLElement)
      .getByText('Agent Breakdown')
      .closest('button')
    expect(workflow).not.toBeNull()
    expect(simplifyWorkflow).not.toBeNull()
    expect(phaseBreakdown).not.toBeNull()
    expect(agentBreakdown).not.toBeNull()
    expect(workflow).toBeEnabled()
    expect(simplifyWorkflow).toBeEnabled()
    expect(phaseBreakdown).toBeEnabled()
    expect(agentBreakdown).toBeEnabled()

    fireEvent.click(workflow as HTMLButtonElement)

    expect(onSplitNode).toHaveBeenCalledWith('root', 'workflow')
  })

  it('allows locked nodes to split while keeping finish task disabled', () => {
    renderTreeGraph(
      buildSnapshot({
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'root',
          node_registry: [buildNode({ status: 'locked' })],
        },
      }),
    )

    fireEvent.click(
      within(screen.getByTestId('rf-node-root')).getByRole('button', { name: 'Node actions' }),
    )

    const aiPlanningSection = screen.getByText('AI Planning').closest('div')
    expect(aiPlanningSection).not.toBeNull()
    expect(within(aiPlanningSection as HTMLElement).getByText('Workflow').closest('button')).toBeEnabled()
    expect(
      within(aiPlanningSection as HTMLElement).getByText('Simplify Workflow').closest('button'),
    ).toBeEnabled()
    expect(
      within(aiPlanningSection as HTMLElement).getByText('Phase Breakdown').closest('button'),
    ).toBeEnabled()
    expect(
      within(aiPlanningSection as HTMLElement).getByText('Agent Breakdown').closest('button'),
    ).toBeEnabled()
    expect(screen.getByRole('button', { name: /Finish Task/i })).toBeDisabled()
  })

  it('disables split actions when a split is already in progress', () => {
    renderTreeGraph(buildSnapshot(), { isSplittingNode: true })

    fireEvent.click(
      within(screen.getByTestId('rf-node-root')).getByRole('button', { name: 'Node actions' }),
    )

    expect(screen.getAllByRole('button', { name: /Splitting.../i })).toHaveLength(4)
    expect(screen.getAllByRole('button', { name: /Splitting.../i })[0]).toBeDisabled()
    expect(screen.getAllByRole('button', { name: /Splitting.../i })[1]).toBeDisabled()
    expect(screen.getAllByRole('button', { name: /Splitting.../i })[2]).toBeDisabled()
    expect(screen.getAllByRole('button', { name: /Splitting.../i })[3]).toBeDisabled()
    expect(screen.getByText('AI planning in progress...')).toBeInTheDocument()
  })

  it('does not recompute layout when only callback props change', () => {
    const snapshot = buildSnapshot()
    const initialProps = {
      snapshot,
      selectedNodeId: snapshot.tree_state.active_node_id,
      isCreatingNode: false,
      isSplittingNode: false,
      isResettingProject: false,
      isResetDisabled: false,
      splittingNodeId: null,
      onSelectNode: vi.fn(async () => undefined),
      onCreateChild: vi.fn(async () => undefined),
      onSplitNode: vi.fn(async () => undefined),
      onOpenBreadcrumb: vi.fn(async () => undefined),
      onFinishTask: vi.fn(async () => undefined),
      onResetProject: vi.fn(async () => undefined),
    }

    const { rerender } = render(<TreeGraph {...initialProps} />)

    expect(layoutSpy).toHaveBeenCalledTimes(1)

    rerender(
      <TreeGraph
        {...initialProps}
        onSelectNode={vi.fn(async () => undefined)}
        onCreateChild={vi.fn(async () => undefined)}
        onSplitNode={vi.fn(async () => undefined)}
        onOpenBreadcrumb={vi.fn(async () => undefined)}
        onFinishTask={vi.fn(async () => undefined)}
      />,
    )

    expect(layoutSpy).toHaveBeenCalledTimes(1)
  })

  it('closes the detail panel when the focused node is removed from the snapshot', () => {
    const snapshot = buildSnapshot({
      tree_state: {
        root_node_id: 'root',
        active_node_id: 'child-1',
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
          }),
        ],
      },
    })

    const { rerender } = render(
      <TreeGraph
        snapshot={snapshot}
        selectedNodeId={snapshot.tree_state.active_node_id}
        isCreatingNode={false}
        isSplittingNode={false}
        isResettingProject={false}
        isResetDisabled={false}
        splittingNodeId={null}
        onSelectNode={vi.fn(async () => undefined)}
        onCreateChild={vi.fn(async () => undefined)}
        onSplitNode={vi.fn(async () => undefined)}
        onOpenBreadcrumb={vi.fn(async () => undefined)}
        onFinishTask={vi.fn(async () => undefined)}
        onResetProject={vi.fn(async () => undefined)}
      />,
    )

    fireEvent.click(within(screen.getByTestId('graph-node-child-1')).getByRole('button', { name: 'Node details' }))
    expect(screen.getByText('Frame editor is being reworked.')).toBeInTheDocument()

    rerender(
      <TreeGraph
        snapshot={buildSnapshot()}
        selectedNodeId="root"
        isCreatingNode={false}
        isSplittingNode={false}
        isResettingProject={false}
        isResetDisabled={false}
        splittingNodeId={null}
        onSelectNode={vi.fn(async () => undefined)}
        onCreateChild={vi.fn(async () => undefined)}
        onSplitNode={vi.fn(async () => undefined)}
        onOpenBreadcrumb={vi.fn(async () => undefined)}
        onFinishTask={vi.fn(async () => undefined)}
        onResetProject={vi.fn(async () => undefined)}
      />,
    )

    expect(screen.queryByText('Frame editor is being reworked.')).not.toBeInTheDocument()
  })
})
