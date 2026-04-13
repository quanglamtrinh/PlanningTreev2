import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ThreadSnapshotV3 } from '../../src/api/types'
import { MessagesV3 } from '../../src/features/conversation/components/v3/MessagesV3'
import {
  buildParseCacheKey,
  PARSE_CACHE_RENDERER_VERSION,
} from '../../src/features/conversation/components/v3/parseCacheContract'
import {
  resetMessagesV3ProfilingHooks,
  resetMessagesV3ProfilingState,
  setMessagesV3ProfilingHooks,
  type ParseCacheTraceEvent,
  type RowRenderProfileEvent,
} from '../../src/features/conversation/components/v3/messagesV3ProfilingHooks'

function makeSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
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
    items: [],
    uiSignals: {
      planReady: {
        planItemId: null,
        revision: null,
        ready: false,
        failed: false,
      },
      activeUserInputRequests: [],
    },
    ...overrides,
  }
}

afterEach(() => {
  resetMessagesV3ProfilingHooks()
  resetMessagesV3ProfilingState()
})

describe('MessagesV3 profiling hooks', () => {
  it('tracks row rerender baseline and parse cache trace events without changing behavior', () => {
    const rowEvents: RowRenderProfileEvent[] = []
    const parseEvents: ParseCacheTraceEvent[] = []
    setMessagesV3ProfilingHooks({
      onRowRender: (event) => {
        rowEvents.push(event)
      },
      onParseCacheTrace: (event) => {
        parseEvents.push(event)
      },
    })

    const onResolveUserInput = vi.fn().mockResolvedValue(undefined)
    const firstSnapshot = makeSnapshot({
      items: [
        {
          id: 'msg-1',
          kind: 'message',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 1,
          createdAt: '2026-04-13T00:00:01Z',
          updatedAt: '2026-04-13T00:00:01Z',
          status: 'completed',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          role: 'assistant',
          text: 'First',
          format: 'markdown',
        },
        {
          id: 'msg-2',
          kind: 'message',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 2,
          createdAt: '2026-04-13T00:00:02Z',
          updatedAt: '2026-04-13T00:00:02Z',
          status: 'completed',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          role: 'assistant',
          text: 'Second',
          format: 'markdown',
        },
      ],
    })

    const { rerender } = render(
      <MessagesV3 snapshot={firstSnapshot} isLoading={false} onResolveUserInput={onResolveUserInput} />,
    )

    const secondSnapshot = makeSnapshot({
      items: [
        {
          ...firstSnapshot.items[0],
        },
        {
          ...firstSnapshot.items[1],
          updatedAt: '2026-04-13T00:00:03Z',
          text: 'Second updated',
        },
      ],
      snapshotVersion: 2,
      updatedAt: '2026-04-13T00:00:03Z',
    })

    rerender(<MessagesV3 snapshot={secondSnapshot} isLoading={false} onResolveUserInput={onResolveUserInput} />)

    const rowRenderCountByItem = rowEvents.reduce<Record<string, number>>((acc, event) => {
      acc[event.itemId] = (acc[event.itemId] ?? 0) + 1
      return acc
    }, {})
    expect(rowRenderCountByItem['msg-1']).toBeGreaterThanOrEqual(2)
    expect(rowRenderCountByItem['msg-2']).toBeGreaterThanOrEqual(2)

    const msg1Key = buildParseCacheKey({
      threadId: 'thread-1',
      itemId: 'msg-1',
      updatedAt: '2026-04-13T00:00:01Z',
      mode: 'message_markdown',
      rendererVersion: PARSE_CACHE_RENDERER_VERSION,
    })
    const msg2InitialKey = buildParseCacheKey({
      threadId: 'thread-1',
      itemId: 'msg-2',
      updatedAt: '2026-04-13T00:00:02Z',
      mode: 'message_markdown',
      rendererVersion: PARSE_CACHE_RENDERER_VERSION,
    })
    const msg2UpdatedKey = buildParseCacheKey({
      threadId: 'thread-1',
      itemId: 'msg-2',
      updatedAt: '2026-04-13T00:00:03Z',
      mode: 'message_markdown',
      rendererVersion: PARSE_CACHE_RENDERER_VERSION,
    })

    expect(parseEvents.some((event) => event.key === msg1Key && event.hit === false)).toBe(true)
    expect(parseEvents.some((event) => event.key === msg1Key && event.hit === true)).toBe(true)
    expect(parseEvents.some((event) => event.key === msg2InitialKey && event.hit === false)).toBe(true)
    expect(parseEvents.some((event) => event.key === msg2UpdatedKey && event.hit === false)).toBe(true)
  })
})
