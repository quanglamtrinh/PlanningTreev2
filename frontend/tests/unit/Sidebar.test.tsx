import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Sidebar } from '../../src/features/graph/Sidebar'
import { useCodexStore } from '../../src/stores/codex-store'
import { useProjectStore } from '../../src/stores/project-store'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-path">{`${location.pathname}${location.search}`}</div>
}

describe('Sidebar', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    useProjectStore.setState(useProjectStore.getInitialState())
    useCodexStore.setState(useCodexStore.getInitialState())
    useProjectStore.setState({
      projects: [],
      activeProjectId: null,
      isLoadingProjects: false,
      snapshot: null,
      selectedNodeId: null,
    })
  })

  afterEach(() => {
    vi.useRealTimers()
    delete window.electronAPI
  })

  it('renders live session and weekly usage from the codex snapshot', () => {
    useCodexStore.setState({
      snapshot: {
        account: null,
        rate_limits: {
          primary: {
            used_percent: 8,
            window_duration_mins: 300,
            resets_at: Date.parse('2026-01-01T02:00:00Z') / 1000,
          },
          secondary: {
            used_percent: 49,
            window_duration_mins: 10_080,
            resets_at: Date.parse('2026-01-07T00:00:00Z') / 1000,
          },
          credits: {
            has_credits: true,
            unlimited: false,
            balance: '4',
          },
          plan_type: 'plus',
        },
      },
    })

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )

    expect(screen.getByText('Session')).toBeInTheDocument()
    expect(screen.getByText('Weekly')).toBeInTheDocument()
    expect(screen.getByText('8%')).toBeInTheDocument()
    expect(screen.getByText('49%')).toBeInTheDocument()
    expect(screen.getByText('· Resets 2h')).toBeInTheDocument()
    expect(screen.getByText('· Resets 6d')).toBeInTheDocument()
    expect(screen.getByText('Credits: 4 credits')).toBeInTheDocument()
  })

  it('hides weekly usage and shows fallback session text when data is missing', () => {
    useCodexStore.setState({
      snapshot: {
        account: null,
        rate_limits: {
          primary: null,
          secondary: null,
          credits: null,
          plan_type: null,
        },
      },
    })

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )

    expect(screen.getByText('Session')).toBeInTheDocument()
    expect(screen.queryByText('Weekly')).not.toBeInTheDocument()
    expect(screen.getAllByText('--')).toHaveLength(1)
  })

  it('uses the Electron folder picker to attach a project folder', async () => {
    vi.useRealTimers()
    const attachProjectFolder = vi.fn().mockResolvedValue(undefined)
    const selectFolder = vi.fn().mockResolvedValue('C:/workspace/demo')
    window.electronAPI = {
      selectFolder,
      getAuthToken: vi.fn(),
      getBackendPort: vi.fn(),
      getAppVersion: vi.fn(),
      setWindowTitle: vi.fn(),
      isElectron: true,
    }
    useProjectStore.setState({
      attachProjectFolder,
    })

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Add project folder' }))

    await waitFor(() => {
      expect(selectFolder).toHaveBeenCalled()
      expect(attachProjectFolder).toHaveBeenCalledWith('C:/workspace/demo')
    })
  })

  it('does nothing when the Electron folder picker is canceled', async () => {
    vi.useRealTimers()
    const attachProjectFolder = vi.fn().mockResolvedValue(undefined)
    const selectFolder = vi.fn().mockResolvedValue(null)
    window.electronAPI = {
      selectFolder,
      getAuthToken: vi.fn(),
      getBackendPort: vi.fn(),
      getAppVersion: vi.fn(),
      setWindowTitle: vi.fn(),
      isElectron: true,
    }
    useProjectStore.setState({
      attachProjectFolder,
    })

    render(
      <MemoryRouter>
        <Sidebar />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Add project folder' }))

    await waitFor(() => {
      expect(selectFolder).toHaveBeenCalled()
    })
    expect(attachProjectFolder).not.toHaveBeenCalled()
  })

  it('opens breadcrumb on double-click for a done node in the sidebar tree', async () => {
    vi.useRealTimers()
    const selectNode = vi.fn().mockResolvedValue(undefined)
    useProjectStore.setState({
      projects: [
        {
          id: 'project-1',
          name: 'Project 1',
          root_goal: 'Goal',
          project_path: 'C:/workspace/project-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      activeProjectId: 'project-1',
      selectedNodeId: 'done-node',
      selectNode,
      snapshot: {
        schema_version: 6,
        project: {
          id: 'project-1',
          name: 'Project 1',
          root_goal: 'Goal',
          project_path: 'C:/workspace/project-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'done-node',
          node_registry: [
            {
              node_id: 'root',
              parent_id: null,
              child_ids: ['done-node'],
              title: 'Root',
              description: '',
              status: 'draft',
              node_kind: 'root',
              depth: 0,
              display_order: 0,
              hierarchical_number: '1',
              is_superseded: false,
              created_at: '2026-01-01T00:00:00Z',
              workflow: {
                frame_confirmed: false,
                active_step: 'frame',
                spec_confirmed: false,
              },
            },
            {
              node_id: 'done-node',
              parent_id: 'root',
              child_ids: [],
              title: 'Completed task',
              description: '',
              status: 'done',
              node_kind: 'original',
              depth: 1,
              display_order: 0,
              hierarchical_number: '1.1',
              is_superseded: false,
              created_at: '2026-01-01T00:00:00Z',
              workflow: {
                frame_confirmed: true,
                active_step: 'spec',
                spec_confirmed: true,
              },
            },
          ],
        },
        updated_at: '2026-01-01T00:00:00Z',
      },
    })

    render(
      <MemoryRouter>
        <Sidebar />
        <LocationProbe />
      </MemoryRouter>,
    )

    fireEvent.doubleClick(screen.getByRole('button', { name: /1\.1 Completed task/i }))

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-1/nodes/done-node/chat?thread=ask')
    })
  })

  it('keeps review nodes on the legacy audit surface from the sidebar tree', async () => {
    vi.useRealTimers()
    const selectNode = vi.fn().mockResolvedValue(undefined)
    useProjectStore.setState({
      projects: [
        {
          id: 'project-1',
          name: 'Project 1',
          root_goal: 'Goal',
          project_path: 'C:/workspace/project-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      activeProjectId: 'project-1',
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
        execution_audit_v2_enabled: true,
      },
      selectedNodeId: 'review-node',
      selectNode,
      snapshot: {
        schema_version: 6,
        project: {
          id: 'project-1',
          name: 'Project 1',
          root_goal: 'Goal',
          project_path: 'C:/workspace/project-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'review-node',
          node_registry: [
            {
              node_id: 'root',
              parent_id: null,
              child_ids: ['review-node'],
              title: 'Root',
              description: '',
              status: 'draft',
              node_kind: 'root',
              depth: 0,
              display_order: 0,
              hierarchical_number: '1',
              is_superseded: false,
              created_at: '2026-01-01T00:00:00Z',
              workflow: {
                frame_confirmed: false,
                active_step: 'frame',
                spec_confirmed: false,
              },
            },
            {
              node_id: 'review-node',
              parent_id: 'root',
              child_ids: [],
              title: 'Review',
              description: '',
              status: 'ready',
              node_kind: 'review',
              depth: 1,
              display_order: 0,
              hierarchical_number: '1.R',
              is_superseded: false,
              created_at: '2026-01-01T00:00:00Z',
              workflow: {
                frame_confirmed: true,
                active_step: 'spec',
                spec_confirmed: true,
              },
            },
          ],
        },
        updated_at: '2026-01-01T00:00:00Z',
      },
    })

    render(
      <MemoryRouter>
        <Sidebar />
        <LocationProbe />
      </MemoryRouter>,
    )

    fireEvent.doubleClick(screen.getByRole('button', { name: /1\.R Review/i }))

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-1/nodes/review-node/chat?thread=audit')
    })
  })

  it('keeps review nodes on the legacy audit surface when the V2 flag is disabled', async () => {
    vi.useRealTimers()
    const selectNode = vi.fn().mockResolvedValue(undefined)
    useProjectStore.setState({
      projects: [
        {
          id: 'project-1',
          name: 'Project 1',
          root_goal: 'Goal',
          project_path: 'C:/workspace/project-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
      ],
      activeProjectId: 'project-1',
      bootstrap: {
        ready: true,
        workspace_configured: true,
        codex_available: true,
        codex_path: 'codex',
        execution_audit_v2_enabled: false,
      },
      selectedNodeId: 'review-node',
      selectNode,
      snapshot: {
        schema_version: 6,
        project: {
          id: 'project-1',
          name: 'Project 1',
          root_goal: 'Goal',
          project_path: 'C:/workspace/project-1',
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
        },
        tree_state: {
          root_node_id: 'root',
          active_node_id: 'review-node',
          node_registry: [
            {
              node_id: 'root',
              parent_id: null,
              child_ids: ['review-node'],
              title: 'Root',
              description: '',
              status: 'draft',
              node_kind: 'root',
              depth: 0,
              display_order: 0,
              hierarchical_number: '1',
              is_superseded: false,
              created_at: '2026-01-01T00:00:00Z',
              workflow: {
                frame_confirmed: false,
                active_step: 'frame',
                spec_confirmed: false,
              },
            },
            {
              node_id: 'review-node',
              parent_id: 'root',
              child_ids: [],
              title: 'Review',
              description: '',
              status: 'ready',
              node_kind: 'review',
              depth: 1,
              display_order: 0,
              hierarchical_number: '1.R',
              is_superseded: false,
              created_at: '2026-01-01T00:00:00Z',
              workflow: {
                frame_confirmed: true,
                active_step: 'spec',
                spec_confirmed: true,
              },
            },
          ],
        },
        updated_at: '2026-01-01T00:00:00Z',
      },
    })

    render(
      <MemoryRouter>
        <Sidebar />
        <LocationProbe />
      </MemoryRouter>,
    )

    fireEvent.doubleClick(screen.getByRole('button', { name: /1\.R Review/i }))

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/projects/project-1/nodes/review-node/chat?thread=audit')
    })
  })
})
