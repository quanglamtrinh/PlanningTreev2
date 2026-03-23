import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { BreadcrumbPlaceholder } from '../../src/features/breadcrumb/BreadcrumbPlaceholder'
import { useChatStore } from '../../src/stores/chat-store'
import { useUIStore } from '../../src/stores/ui-store'

vi.mock('../../src/features/breadcrumb/BreadcrumbChatView', () => ({
  BreadcrumbChatView: () => <div>Breadcrumb chat stub</div>,
}))

describe('BreadcrumbPlaceholder', () => {
  beforeEach(() => {
    useUIStore.setState({ ...useUIStore.getInitialState(), activeSurface: 'graph' })
    useChatStore.setState(useChatStore.getInitialState())
  })

  it('renders chat and marks breadcrumb as the active surface', () => {
    render(
      <MemoryRouter initialEntries={['/projects/project-1/nodes/root/chat']}>
        <Routes>
          <Route path="/projects/:projectId/nodes/:nodeId/chat" element={<BreadcrumbPlaceholder />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('Breadcrumb chat stub')).toBeInTheDocument()
    expect(useUIStore.getState().activeSurface).toBe('breadcrumb')
  })
})
