import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ConversationItemV3, ThreadSnapshotV3 } from '../../src/api/types'
import { MessagesV3, normalizeMessagesV3Phase10Mode } from '../../src/features/conversation/components/v3/MessagesV3'
import {
  resetMessagesV3ProfilingHooks,
  setMessagesV3ProfilingHooks,
  type Phase10FallbackEvent,
  type Phase10ProgressiveBatchEvent,
} from '../../src/features/conversation/components/v3/messagesV3ProfilingHooks'

function makeMessageItem(index: number, idPrefix = 'msg'): Extract<ConversationItemV3, { kind: 'message' }> {
  const itemId = `${idPrefix}-${index}`
  return {
    id: itemId,
    kind: 'message',
    threadId: 'thread-1',
    turnId: 'turn-1',
    sequence: index + 1,
    createdAt: `2026-04-13T00:00:${String(index % 60).padStart(2, '0')}Z`,
    updatedAt: `2026-04-13T00:01:${String(index % 60).padStart(2, '0')}Z`,
    status: 'completed',
    source: 'upstream',
    tone: 'neutral',
    metadata: {},
    role: 'assistant',
    text: `Message ${index}`,
    format: 'markdown',
  }
}

function makeSnapshotWithMessages(messageCount: number, idPrefix = 'msg'): ThreadSnapshotV3 {
  return {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadId: 'thread-1',
    threadRole: 'execution',
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-04-13T00:00:00Z',
    updatedAt: '2026-04-13T00:00:00Z',
    items: Array.from({ length: messageCount }, (_, index) => makeMessageItem(index, idPrefix)),
    uiSignals: {
      planReady: {
        planItemId: null,
        revision: null,
        ready: false,
        failed: false,
      },
      activeUserInputRequests: [],
    },
  }
}

afterEach(() => {
  resetMessagesV3ProfilingHooks()
  vi.restoreAllMocks()
})

describe('MessagesV3 Phase 10 mode and rendering behavior', () => {
  it('normalizes phase10 mode values and defaults invalid input to off', () => {
    expect(normalizeMessagesV3Phase10Mode(undefined)).toBe('off')
    expect(normalizeMessagesV3Phase10Mode(null)).toBe('off')
    expect(normalizeMessagesV3Phase10Mode('off')).toBe('off')
    expect(normalizeMessagesV3Phase10Mode('shadow')).toBe('shadow')
    expect(normalizeMessagesV3Phase10Mode('on')).toBe('on')
    expect(normalizeMessagesV3Phase10Mode('ON')).toBe('on')
    expect(normalizeMessagesV3Phase10Mode('invalid-mode')).toBe('off')
  })

  it('progressively mounts grouped entries in batches while preserving order', () => {
    const rafQueue: FrameRequestCallback[] = []
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((callback: FrameRequestCallback) => {
      rafQueue.push(callback)
      return rafQueue.length
    })
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => undefined)

    const progressiveEvents: Phase10ProgressiveBatchEvent[] = []
    setMessagesV3ProfilingHooks({
      onPhase10ProgressiveBatch: (event) => progressiveEvents.push(event),
    })

    render(
      <MessagesV3
        snapshot={makeSnapshotWithMessages(260)}
        isLoading={false}
        onResolveUserInput={() => Promise.resolve()}
        phase10ModeOverride="on"
      />,
    )

    const initialHosts = screen.getAllByTestId('messages-v3-stream-entry-host')
    expect(initialHosts).toHaveLength(120)
    expect(initialHosts[0]).toHaveAttribute('data-stream-entry-key', 'item:msg-0')
    expect(initialHosts[initialHosts.length - 1]).toHaveAttribute('data-stream-entry-key', 'item:msg-119')

    act(() => {
      const pending = [...rafQueue]
      rafQueue.length = 0
      pending.forEach((callback, index) => callback((index + 1) * 16))
    })

    const afterOneFrameHosts = screen.getAllByTestId('messages-v3-stream-entry-host')
    expect(afterOneFrameHosts).toHaveLength(160)
    expect(afterOneFrameHosts[0]).toHaveAttribute('data-stream-entry-key', 'item:msg-0')
    expect(afterOneFrameHosts[afterOneFrameHosts.length - 1]).toHaveAttribute(
      'data-stream-entry-key',
      'item:msg-159',
    )
    expect(progressiveEvents.length).toBeGreaterThan(0)
  })

  it('virtualizes stream hosts in on mode for very long lists', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshotWithMessages(420)}
        isLoading={false}
        onResolveUserInput={() => Promise.resolve()}
        phase10ModeOverride="on"
      />,
    )

    expect(screen.getByTestId('messages-v3-virtualized-viewport')).toBeInTheDocument()
    const hosts = screen.getAllByTestId('messages-v3-stream-entry-host')
    expect(hosts.length).toBeGreaterThan(0)
    expect(hosts.length).toBeLessThan(120)
  })

  it('keeps full stream rendering in shadow mode', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshotWithMessages(260)}
        isLoading={false}
        onResolveUserInput={() => Promise.resolve()}
        phase10ModeOverride="shadow"
      />,
    )

    const streamStack = screen.getByTestId('messages-v3-stream-stack')
    expect(streamStack).toHaveAttribute('data-phase10-mode', 'shadow')
    expect(screen.getAllByTestId('messages-v3-stream-entry-host')).toHaveLength(260)
    expect(screen.queryByTestId('messages-v3-virtualized-viewport')).not.toBeInTheDocument()
  })

  it('activates thread-local fallback when anchor key disappears', () => {
    const fallbackEvents: Phase10FallbackEvent[] = []
    setMessagesV3ProfilingHooks({
      onPhase10Fallback: (event) => fallbackEvents.push(event),
    })

    const { rerender } = render(
      <MessagesV3
        snapshot={makeSnapshotWithMessages(260, 'first')}
        isLoading={false}
        onResolveUserInput={() => Promise.resolve()}
        phase10ModeOverride="on"
      />,
    )

    const feed = screen.getByTestId('messages-v3-feed')
    Object.defineProperty(feed, 'scrollHeight', { configurable: true, value: 4000 })
    Object.defineProperty(feed, 'clientHeight', { configurable: true, value: 400 })
    feed.scrollTop = 120
    fireEvent.scroll(feed)

    rerender(
      <MessagesV3
        snapshot={makeSnapshotWithMessages(260, 'second')}
        isLoading={false}
        onResolveUserInput={() => Promise.resolve()}
        phase10ModeOverride="on"
      />,
    )

    const streamStack = screen.getByTestId('messages-v3-stream-stack')
    expect(streamStack).toHaveAttribute('data-phase10-fallback', 'anchor_missing')
    expect(fallbackEvents.length).toBeGreaterThan(0)
    expect(fallbackEvents[0]?.reason).toBe('anchor_missing')
  })
})
