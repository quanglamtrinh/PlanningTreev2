import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ComposerPane } from '../../src/features/session_v2/components/ComposerPane'

describe('ComposerPane', () => {
  it('routes slash text to command popup and submits on Enter', async () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    render(
      <ComposerPane
        isTurnRunning={false}
        onSubmit={onSubmit}
        onInterrupt={onInterrupt}
      />,
    )

    const textarea = screen.getByPlaceholderText('Start new turn...') as HTMLTextAreaElement
    fireEvent.change(textarea, { target: { value: '/plan investigate' } })
    expect(screen.getByText('/plan')).toBeInTheDocument()

    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('enables reverse search with Ctrl+R', () => {
    const onSubmit = vi.fn(async () => undefined)
    const onInterrupt = vi.fn(async () => undefined)
    render(
      <ComposerPane
        isTurnRunning={false}
        onSubmit={onSubmit}
        onInterrupt={onInterrupt}
      />,
    )
    const textarea = screen.getByPlaceholderText('Start new turn...') as HTMLTextAreaElement
    fireEvent.keyDown(textarea, { key: 'r', ctrlKey: true })
    expect(screen.getByPlaceholderText('Search history')).toBeInTheDocument()
  })
})

