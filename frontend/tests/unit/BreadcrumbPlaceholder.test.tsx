import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BreadcrumbPlaceholder } from '../../src/features/breadcrumb/BreadcrumbPlaceholder'
import { useChatStore } from '../../src/stores/chat-store'
import { useUIStore } from '../../src/stores/ui-store'

vi.mock('../../src/features/breadcrumb/BreadcrumbChatView', () => ({
  BreadcrumbChatView: () => <div>Breadcrumb chat stub</div>,
}))

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-path">{location.pathname}</div>
}

describe('BreadcrumbPlaceholder', () => {
  beforeEach(() => {
    useUIStore.setState({ ...useUIStore.getInitialState(), activeSurface: 'graph' })
    useChatStore.setState(useChatStore.getInitialState())
  })

  it('renders chat and a floating back control; marks breadcrumb as the active surface', () => {
    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbPlaceholder />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByRole('button', { name: 'Back to Graph' })).toBeInTheDocument()
    expect(screen.getByText('Breadcrumb chat stub')).toBeInTheDocument()
    expect(useUIStore.getState().activeSurface).toBe('breadcrumb')
  })

  it('navigates back to the graph route from the back button', () => {
    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat']}>
        <Routes>
          <Route path="/" element={<div>Graph workspace stub</div>} />
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbPlaceholder />} />
        </Routes>
        <LocationProbe />
      </MemoryRouter>,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Back to Graph' }))

    expect(screen.getByText('Graph workspace stub')).toBeInTheDocument()
    expect(screen.getByTestId('location-path').textContent).toBe('/')
    expect(useUIStore.getState().activeSurface).toBe('graph')
  })
})
