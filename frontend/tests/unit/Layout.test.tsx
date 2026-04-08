import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { initializeCodexMock, disconnectCodexMock } = vi.hoisted(() => ({
  initializeCodexMock: vi.fn(() => Promise.resolve()),
  disconnectCodexMock: vi.fn(),
}))

vi.mock('../../src/stores/codex-store', () => ({
  useCodexStore: (selector: (state: {
    initialize: typeof initializeCodexMock
    disconnect: typeof disconnectCodexMock
  }) => unknown) =>
    selector({
      initialize: initializeCodexMock,
      disconnect: disconnectCodexMock,
    }),
}))

import { Layout } from '../../src/components/Layout'
import { useUIStore } from '../../src/stores/ui-store'

describe('Layout', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    useUIStore.setState(useUIStore.getInitialState())
    useUIStore.setState({ theme: 'default' })
  })

  it('renders six theme options', () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>workspace</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Canvas' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Terracotta' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fjord' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Moss' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Graphite' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Aurora' })).toBeInTheDocument()
  })

  it('removes data-theme for default and applies explicit theme selections', () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>workspace</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(document.documentElement).not.toHaveAttribute('data-theme')

    fireEvent.click(screen.getByRole('button', { name: 'Terracotta' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'warm-earth')

    fireEvent.click(screen.getByRole('button', { name: 'Canvas' }))
    expect(document.documentElement).not.toHaveAttribute('data-theme')
  })

  it('does not show Back to Graph on the graph route', () => {
    render(
      <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>workspace</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.queryByRole('button', { name: 'Back to Graph' })).not.toBeInTheDocument()
  })

  it('shows Back to Graph on breadcrumb chat route and navigates to graph', () => {
    render(
      <MemoryRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        initialEntries={['/projects/project-1/nodes/root/chat']}
      >
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>Graph workspace stub</div>} />
            <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<div>breadcrumb chat</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Back to Graph' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Back to Graph' }))

    expect(screen.getByText('Graph workspace stub')).toBeInTheDocument()
    expect(useUIStore.getState().activeSurface).toBe('graph')
  })

  it('shows Back to Graph on hidden breadcrumb V2 route', () => {
    render(
      <MemoryRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        initialEntries={['/projects/project-1/nodes/root/chat-v2']}
      >
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>Graph workspace stub</div>} />
            <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<div>breadcrumb chat v2</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Back to Graph' })).toBeInTheDocument()
  })

  it('shows Back to Graph on usage snapshot route and navigates to graph', () => {
    render(
      <MemoryRouter
        future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        initialEntries={['/usage-snapshot']}
      >
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<div>Graph workspace stub</div>} />
            <Route path="/usage-snapshot" element={<div>Usage snapshot stub</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Back to Graph' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Back to Graph' }))

    expect(screen.getByText('Graph workspace stub')).toBeInTheDocument()
  })
})
