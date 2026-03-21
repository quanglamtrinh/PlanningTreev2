import { render, screen } from '@testing-library/react'
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
})
