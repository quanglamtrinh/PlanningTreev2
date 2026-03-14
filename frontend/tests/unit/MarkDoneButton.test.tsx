import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { MarkDoneButton } from '../../src/features/breadcrumb/MarkDoneButton'
import { useProjectStore } from '../../src/stores/project-store'

const readyLeafNode = {
  node_id: 'node-1',
  parent_id: null,
  child_ids: [],
  title: 'Leaf task',
  description: 'Execute the task',
  status: 'ready' as const,
  phase: 'ready_for_execution' as const,
  planning_mode: null,
  depth: 0,
  display_order: 0,
  hierarchical_number: '1',
  split_metadata: null,
  chat_session_id: null,
  has_ask_thread: false,
  ask_thread_status: null,
  is_superseded: false,
  created_at: '2026-03-08T00:00:00Z',
}

describe('MarkDoneButton', () => {
  beforeEach(() => {
    useProjectStore.setState(useProjectStore.getInitialState())
  })

  it('enables leaf ready nodes and completes them on click', async () => {
    const completeNode = vi.fn(async () => undefined)
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      snapshot: {
        schema_version: 2,
        project: {
          id: 'project-1',
          name: 'Alpha',
          root_goal: 'Ship phase 4',
          base_workspace_root: 'C:/workspace',
          project_workspace_root: 'C:/workspace/alpha',
          created_at: '2026-03-08T00:00:00Z',
          updated_at: '2026-03-08T00:00:00Z',
        },
        tree_state: {
          root_node_id: 'node-1',
          active_node_id: 'node-1',
          node_registry: [readyLeafNode],
        },
        updated_at: '2026-03-08T00:00:00Z',
      },
      completeNode,
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MarkDoneButton projectId="project-1" nodeId="node-1" node={readyLeafNode} />
      </MemoryRouter>,
    )

    const button = screen.getByRole('button', { name: 'Mark Done' })
    expect(button).toBeEnabled()

    fireEvent.click(button)

    await waitFor(() => {
      expect(completeNode).toHaveBeenCalledWith('node-1')
    })
  })

  it('disables non-leaf nodes', () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      snapshot: {
        schema_version: 2,
        project: {
          id: 'project-1',
          name: 'Alpha',
          root_goal: 'Ship phase 4',
          base_workspace_root: 'C:/workspace',
          project_workspace_root: 'C:/workspace/alpha',
          created_at: '2026-03-08T00:00:00Z',
          updated_at: '2026-03-08T00:00:00Z',
        },
        tree_state: {
          root_node_id: 'node-1',
          active_node_id: 'node-1',
          node_registry: [
            { ...readyLeafNode, child_ids: ['child-1'] },
            {
              ...readyLeafNode,
              node_id: 'child-1',
              parent_id: 'node-1',
              hierarchical_number: '1.1',
            },
          ],
        },
        updated_at: '2026-03-08T00:00:00Z',
      },
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MarkDoneButton
          projectId="project-1"
          nodeId="node-1"
          node={{ ...readyLeafNode, child_ids: ['child-1'] }}
        />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Mark Done' })).toBeDisabled()
  })

  it('disables nodes that have not reached execution readiness', () => {
    useProjectStore.setState({
      ...useProjectStore.getInitialState(),
      snapshot: {
        schema_version: 2,
        project: {
          id: 'project-1',
          name: 'Alpha',
          root_goal: 'Ship phase 4',
          base_workspace_root: 'C:/workspace',
          project_workspace_root: 'C:/workspace/alpha',
          created_at: '2026-03-08T00:00:00Z',
          updated_at: '2026-03-08T00:00:00Z',
        },
        tree_state: {
          root_node_id: 'node-1',
          active_node_id: 'node-1',
          node_registry: [{ ...readyLeafNode, phase: 'planning' as const }],
        },
        updated_at: '2026-03-08T00:00:00Z',
      },
    })

    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <MarkDoneButton
          projectId="project-1"
          nodeId="node-1"
          node={{ ...readyLeafNode, phase: 'planning' as const }}
        />
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Mark Done' })).toBeDisabled()
  })
})
