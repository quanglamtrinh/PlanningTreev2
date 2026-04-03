import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { MessagesV3ErrorBoundary } from '../../src/features/conversation/components/v3/MessagesV3ErrorBoundary'

function Thrower() {
  throw new Error('boom')
}

describe('MessagesV3ErrorBoundary', () => {
  it('renders fallback and calls onRenderError when child throws', () => {
    const onRenderError = vi.fn()
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    try {
      render(
        <MessagesV3ErrorBoundary onRenderError={onRenderError}>
          <Thrower />
        </MessagesV3ErrorBoundary>,
      )
    } finally {
      spy.mockRestore()
    }

    expect(screen.getByTestId('messages-v3-render-error')).toBeInTheDocument()
    expect(onRenderError).toHaveBeenCalledTimes(1)
    expect(onRenderError.mock.calls[0][0]).toBeInstanceOf(Error)
  })
})
