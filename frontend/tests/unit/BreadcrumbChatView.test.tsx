import { render, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { BreadcrumbChatView } from '../../src/features/breadcrumb/BreadcrumbChatView'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-path">{`${location.pathname}${location.search}`}</div>
}

describe('BreadcrumbChatView', () => {
  it('redirects legacy chat route to chat-v2 ask', async () => {
    const { getByTestId } = render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat?thread=execution']}>
        <LocationProbe />
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbChatView />} />
          <Route path="/projects/:projectId/nodes/:nodeId/chat-v2" element={<div />} />
        </Routes>
      </MemoryRouter>,
    )

    await waitFor(() => {
      expect(getByTestId('location-path').textContent).toBe('/projects/project-1/nodes/root/chat-v2?thread=ask')
    })
  })
})
