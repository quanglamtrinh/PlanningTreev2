import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { initializeMock, projectStoreState } = vi.hoisted(() => {
  const initializeMock = vi.fn(async () => undefined)
  const projectStoreState = {
    initialize: initializeMock,
    hasInitialized: true,
    isInitializing: false,
  }
  return { initializeMock, projectStoreState }
})

vi.mock('../../src/features/graph/Sidebar', () => ({
  Sidebar: () => <aside data-testid="sidebar-stub" />,
}))

vi.mock('../../src/stores/project-store', () => ({
  useProjectStore: (selector: (state: typeof projectStoreState) => unknown) => selector(projectStoreState),
}))

import { SkillsPage } from '../../src/features/skills/SkillsPage'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-path">{location.pathname}</div>
}

describe('SkillsPage', () => {
  beforeEach(() => {
    initializeMock.mockClear()
    projectStoreState.hasInitialized = true
    projectStoreState.isInitializing = false
  })

  it('renders global skills before the add skill form', () => {
    render(
      <MemoryRouter>
        <SkillsPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('sidebar-stub')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Global skills registry' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Global skills' })).toBeInTheDocument()
    expect(screen.getByText('Structured output')).toBeInTheDocument()
    expect(screen.getByText('progress-updates/SKILL.md')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Add skill' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add skill' })).toBeDisabled()
  })

  it('adds a skill from the simple form into local UI state', async () => {
    render(
      <MemoryRouter>
        <SkillsPage />
      </MemoryRouter>,
    )

    fireEvent.change(screen.getByLabelText('Skill name'), { target: { value: 'Browser automation' } })
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Drive browser workflows.' } })
    fireEvent.change(screen.getByLabelText('Repo path'), { target: { value: '.codex/skills/browser-automation' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add skill' }))

    await waitFor(() => {
      expect(screen.getByText('Browser automation')).toBeInTheDocument()
    })
    expect(screen.getByText('browser-automation/SKILL.md', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('Added Browser automation to this UI session.')).toBeInTheDocument()
  })

  it('shows the manual skill.md template in Rich View and can add it locally', async () => {
    render(
      <MemoryRouter>
        <SkillsPage />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('tab', { name: 'Manual skill.md' }))
    fireEvent.click(screen.getByRole('button', { name: 'Rich View' }))

    const richView = screen.getByTestId('manual-skill-rich-view')
    expect(within(richView).getByRole('heading', { name: 'Skill' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add manual skill' }))

    await waitFor(() => {
      expect(screen.getAllByText('Skill').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('Added Skill from manual skill.md.')).toBeInTheDocument()
  })

  it('navigates back to graph from the back button', async () => {
    render(
      <MemoryRouter initialEntries={['/skills']}>
        <Routes>
          <Route
            path="/skills"
            element={
              <>
                <SkillsPage />
                <LocationProbe />
              </>
            }
          />
          <Route
            path="/graph"
            element={
              <>
                <SkillsPage />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Back to graph' }))

    await waitFor(() => {
      expect(screen.getByTestId('location-path')).toHaveTextContent('/graph')
    })
  })
})
