import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'

import { Layout } from '../../src/components/Layout'
import { useUIStore } from '../../src/stores/ui-store'

describe('Layout', () => {
  beforeEach(() => {
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

    expect(screen.getByRole('button', { name: 'Default' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Warm Earth' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Slate Pro' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Forest' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Obsidian' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Amethyst' })).toBeInTheDocument()
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

    fireEvent.click(screen.getByRole('button', { name: 'Warm Earth' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'warm-earth')

    fireEvent.click(screen.getByRole('button', { name: 'Default' }))
    expect(document.documentElement).not.toHaveAttribute('data-theme')
  })
})
