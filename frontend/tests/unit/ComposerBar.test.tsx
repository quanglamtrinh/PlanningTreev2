import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ComposerBar } from '../../src/features/breadcrumb/ComposerBar'

describe('ComposerBar early response UX', () => {
  it('renders stable early-response labels without layout shift placeholders', () => {
    const onSend = vi.fn()
    const { rerender } = render(
      <ComposerBar onSend={onSend} disabled={false} earlyResponsePhase="idle" />,
    )

    const statusRegion = document.querySelector('[aria-live="polite"]')
    expect(statusRegion).toBeTruthy()

    rerender(<ComposerBar onSend={onSend} disabled={false} earlyResponsePhase="pending_send" />)
    expect(screen.getByText('Sending...')).toBeInTheDocument()

    rerender(<ComposerBar onSend={onSend} disabled={false} earlyResponsePhase="stream_open" />)
    expect(screen.getByText('Agent connected...')).toBeInTheDocument()

    rerender(<ComposerBar onSend={onSend} disabled={false} earlyResponsePhase="first_delta" />)
    expect(screen.getByText('Responding...')).toBeInTheDocument()
  })

  it('submits text and clears input on send', () => {
    const onSend = vi.fn()
    render(<ComposerBar onSend={onSend} disabled={false} earlyResponsePhase="idle" />)

    const input = screen.getByPlaceholderText('Send a message...') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: 'hello world' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))

    expect(onSend).toHaveBeenCalledWith('hello world')
    expect(input.value).toBe('')
  })
})
