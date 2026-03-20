import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { BreadcrumbPlaceholder } from '../../src/features/breadcrumb/BreadcrumbPlaceholder'
import { useUIStore } from '../../src/stores/ui-store'

describe('BreadcrumbPlaceholder', () => {
  beforeEach(() => {
    useUIStore.setState({ ...useUIStore.getInitialState(), activeSurface: 'graph' })
  })

  it('renders the rework placeholder and marks breadcrumb as the active surface', () => {
    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbPlaceholder />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Breadcrumb view is being reworked.')).toBeInTheDocument()
    expect(
      screen.getByText(/temporary placeholder while the old breadcrumb workspace is retired/i),
    ).toBeInTheDocument()
    expect(useUIStore.getState().activeSurface).toBe('breadcrumb')
  })
})
