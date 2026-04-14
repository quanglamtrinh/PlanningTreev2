import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ConversationMarkdown } from '../../src/features/conversation/components/ConversationMarkdown'

type ObserverEntry = { isIntersecting: boolean }

class MockIntersectionObserver {
  static instances: MockIntersectionObserver[] = []

  readonly callback: IntersectionObserverCallback

  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback
    MockIntersectionObserver.instances.push(this)
  }

  observe = vi.fn()
  disconnect = vi.fn()
  unobserve = vi.fn()
  takeRecords = vi.fn(() => [])

  emit(entry: ObserverEntry) {
    const records = [
      {
        isIntersecting: entry.isIntersecting,
        target: document.createElement('div'),
      },
    ] as unknown as IntersectionObserverEntry[]
    this.callback(records, this as unknown as IntersectionObserver)
  }

  static reset() {
    MockIntersectionObserver.instances = []
  }
}

describe('ConversationMarkdown phase11 lazy mode', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockIntersectionObserver.reset()
    vi.stubGlobal(
      'IntersectionObserver',
      MockIntersectionObserver as unknown as typeof IntersectionObserver,
    )
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('defers markdown parse until row becomes visible', async () => {
    render(
      <ConversationMarkdown
        content={'[Open](https://example.com)'}
        phase11Mode="on"
        phase11DeferredTimeoutMs={5000}
      />, 
    )

    expect(screen.getByTestId('conversation-markdown-lazy-plain')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Open' })).not.toBeInTheDocument()

    const observer = MockIntersectionObserver.instances[0]
    expect(observer).toBeDefined()

    await act(async () => {
      observer.emit({ isIntersecting: true })
    })

    expect(screen.queryByTestId('conversation-markdown-lazy-plain')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Open' })).toBeInTheDocument()
  })

  it('renders markdown after deferred timeout even when still offscreen', async () => {
    render(
      <ConversationMarkdown
        content={'[Deferred](https://example.com)'}
        phase11Mode="on"
        phase11DeferredTimeoutMs={200}
      />, 
    )

    expect(screen.getByTestId('conversation-markdown-lazy-plain')).toBeInTheDocument()

    await act(async () => {
      vi.advanceTimersByTime(250)
    })

    expect(screen.queryByTestId('conversation-markdown-lazy-plain')).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Deferred' })).toBeInTheDocument()
  })
})
