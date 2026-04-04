import { render, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { BreadcrumbPlaceholder } from '../../src/features/breadcrumb/BreadcrumbPlaceholder'
import { useUIStore } from '../../src/stores/ui-store'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-path">{`${location.pathname}${location.search}`}</div>
}

describe('BreadcrumbPlaceholder', () => {
  beforeEach(() => {
    useUIStore.setState({ ...useUIStore.getInitialState(), activeSurface: 'graph' })
  })

  it('marks breadcrumb as active and redirects /chat to /chat-v2 ask', async () => {
    const { getByTestId } = render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat']}>
        <LocationProbe />
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbPlaceholder />} />
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<div />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(getByTestId('location-path').textContent).toBe('/projects/project-1/nodes/root/chat-v2?thread=ask')
    })
    expect(useUIStore.getState().activeSurface).toBe('breadcrumb')
  })
})
