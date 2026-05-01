import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { initializeMock, listSkillsRegistryMock, projectStoreState } = vi.hoisted(() => {
  const initializeMock = vi.fn(async () => undefined)
  const listSkillsRegistryMock = vi.fn(async () => ({
    projectId: 'project-1',
    catalogCwd: 'C:/work/project',
    data: [
      {
        cwd: 'C:/work/project',
        skills: [
          {
            name: 'planning-brief',
            description: 'Plan work before implementation.',
            path: 'C:/work/project/.codex/skills/planning-brief/SKILL.md',
            scope: 'repo',
            enabled: true,
            dependencies: { tools: [] },
          },
        ],
        errors: [],
      },
    ],
  }))
  const projectStoreState = {
    initialize: initializeMock,
    hasInitialized: true,
    isInitializing: false,
    activeProjectId: 'project-1',
  }
  return { initializeMock, listSkillsRegistryMock, projectStoreState }
})

vi.mock('../../src/features/graph/Sidebar', () => ({
  Sidebar: () => <aside data-testid="sidebar-stub" />,
}))

vi.mock('../../src/api/client', () => ({
  api: {
    listSkillsRegistry: listSkillsRegistryMock,
  },
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
    listSkillsRegistryMock.mockClear()
    projectStoreState.hasInitialized = true
    projectStoreState.isInitializing = false
    projectStoreState.activeProjectId = 'project-1'
  })

  it('renders Codex-backed global skills catalog', async () => {
    render(
      <MemoryRouter>
        <SkillsPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('sidebar-stub')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Global skills registry' })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByText('planning-brief')).toBeInTheDocument()
    })
    expect(screen.getByText('C:/work/project/.codex/skills/planning-brief/SKILL.md')).toBeInTheDocument()
    expect(screen.getByText('Catalog cwd: C:/work/project')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Authoring' })).toBeInTheDocument()
    expect(screen.getByText(/Skill authoring is deferred/)).toBeInTheDocument()
    expect(listSkillsRegistryMock).toHaveBeenCalledWith('project-1')
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
