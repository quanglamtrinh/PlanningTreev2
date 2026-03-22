import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { Sidebar } from '../../src/features/graph/Sidebar'
import { useCodexStore } from '../../src/stores/codex-store'
import { useProjectStore } from '../../src/stores/project-store'

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
})
