import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PlanningPanel } from '../../src/features/breadcrumb/PlanningPanel'
import { useProjectStore } from '../../src/stores/project-store'

const snapshot = {
  schema_version: 3,
  project: {
    id: 'project-1',
    name: 'Alpha',
    root_goal: 'Ship phase 3',
    base_workspace_root: 'C:/workspace',
    project_workspace_root: 'C:/workspace/alpha',
    created_at: '2026-03-07T10:00:00Z',
    updated_at: '2026-03-07T10:00:00Z',
  },
  tree_state: {
    root_node_id: 'root',
    active_node_id: 'child-1',
    node_registry: [
      {
        node_id: 'root',
        parent_id: null,
        child_ids: ['child-1'],
        title: 'Root',
        description: 'Root description',
        status: 'draft' as const,
        planning_mode: 'slice' as const,
        depth: 0,
        display_order: 0,
        hierarchical_number: '1',
        split_metadata: null,
        chat_session_id: null,
        has_ask_thread: false,
        ask_thread_status: null,
        has_planning_thread: true,
        has_execution_thread: false,
        planning_thread_status: 'idle' as const,
        execution_thread_status: null,
        is_superseded: false,
        created_at: '2026-03-07T10:00:00Z',
      },
      {
        node_id: 'child-1',
        parent_id: 'root',
        child_ids: [],
        title: 'Child',
        description: 'Child description',
        status: 'ready' as const,
        planning_mode: null,
        depth: 1,
        display_order: 0,
        hierarchical_number: '1.1',
        split_metadata: null,
        chat_session_id: null,
        has_ask_thread: false,
        ask_thread_status: null,
        has_planning_thread: true,
        has_execution_thread: false,
        planning_thread_status: 'idle' as const,
        execution_thread_status: null,
        is_superseded: false,
        created_at: '2026-03-07T10:05:00Z',
      },
    ],
  },
  updated_at: '2026-03-07T10:05:00Z',
}

describe('PlanningPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useProjectStore.setState(useProjectStore.getInitialState())
  })

  it('renders inherited badges and structured split cards', () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      snapshot,
      planningConnectionStatus: 'connected',
      planningHistoryByNode: {
        'child-1': [
          {
            turn_id: 'turn-1',
            role: 'tool_call',
            tool_name: 'emit_render_data',
            is_inherited: true,
            origin_node_id: 'root',
            arguments: {
              kind: 'split_result',
              payload: {
                subtasks: [
                  {
                    order: 1,
                    prompt: 'Setup repo',
                    risk_reason: 'env',
                    what_unblocks: 'coding',
                  },
                ],
              },
            },
            timestamp: '2026-03-07T10:05:00Z',
          },
          {
            turn_id: 'turn-1',
            role: 'assistant',
            content: 'Split completed.',
            is_inherited: true,
            origin_node_id: 'root',
            timestamp: '2026-03-07T10:05:00Z',
          },
        ],
      },
      splitNode: vi.fn(async () => {}),
    })

    render(<PlanningPanel node={snapshot.tree_state.node_registry[1]} />)

    expect(screen.getAllByText('Inherited from 1 Root')).toHaveLength(2)
    expect(screen.getByText('Slice 1')).toBeInTheDocument()
    expect(screen.getByText('Setup repo')).toBeInTheDocument()
    expect(screen.getByText((_, node) => node?.textContent === 'Risk: env')).toBeInTheDocument()
    expect(screen.getByText((_, node) => node?.textContent === 'Unblocks: coding')).toBeInTheDocument()
    expect(screen.getByText('Split completed.')).toBeInTheDocument()
  })

  it('renders context_merge turns with summary and content', () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      snapshot,
      planningConnectionStatus: 'connected',
      planningHistoryByNode: {
        'child-1': [
          {
            turn_id: 'merge-1',
            role: 'context_merge',
            content: 'A shared dependency constraint must be preserved before splitting.',
            summary: 'Preserve dependency constraint',
            packet_id: 'packet-1',
            is_inherited: false,
            origin_node_id: 'child-1',
            timestamp: '2026-03-07T10:06:00Z',
          },
        ],
      },
      splitNode: vi.fn(async () => {}),
    })

    render(<PlanningPanel node={snapshot.tree_state.node_registry[1]} />)

    expect(screen.getByText('Context Merge')).toBeInTheDocument()
    expect(screen.getByText('Preserve dependency constraint')).toBeInTheDocument()
    expect(screen.getByText('A shared dependency constraint must be preserved before splitting.')).toBeInTheDocument()
  })

  it('allows locked nodes to split', () => {
    const splitNode = vi.fn(async () => {})
    const lockedSnapshot = {
      ...snapshot,
      tree_state: {
        ...snapshot.tree_state,
        node_registry: [
          snapshot.tree_state.node_registry[0],
          {
            ...snapshot.tree_state.node_registry[1],
            status: 'locked' as const,
          },
        ],
      },
    }

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      snapshot: lockedSnapshot,
      planningConnectionStatus: 'connected',
      splitNode,
    })

    render(<PlanningPanel node={lockedSnapshot.tree_state.node_registry[1]} />)

    const walkingSkeleton = screen.getByRole('button', { name: /Walking Skeleton/i })
    const slice = screen.getByRole('button', { name: /Slice/i })
    expect(walkingSkeleton).toBeEnabled()
    expect(slice).toBeEnabled()

    fireEvent.click(walkingSkeleton)

    expect(splitNode).toHaveBeenCalledWith('child-1', 'walking_skeleton', false)
  })

  it('keeps split disabled for done nodes', () => {
    const doneSnapshot = {
      ...snapshot,
      tree_state: {
        ...snapshot.tree_state,
        node_registry: [
          snapshot.tree_state.node_registry[0],
          {
            ...snapshot.tree_state.node_registry[1],
            status: 'done' as const,
          },
        ],
      },
    }

    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      snapshot: doneSnapshot,
      planningConnectionStatus: 'connected',
      splitNode: vi.fn(async () => {}),
    })

    render(<PlanningPanel node={doneSnapshot.tree_state.node_registry[1]} />)

    expect(screen.getByRole('button', { name: /Walking Skeleton/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Slice/i })).toBeDisabled()
  })
})
