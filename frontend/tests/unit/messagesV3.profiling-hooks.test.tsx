import { render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ConversationItemV3, ThreadSnapshotV3 } from '../../src/api/types'
import { MessagesV3 } from '../../src/features/conversation/components/v3/MessagesV3'
import {
  buildParseCacheKey,
  PARSE_CACHE_RENDERER_VERSION,
} from '../../src/features/conversation/components/v3/parseCacheContract'
import {
  emitParseCacheTrace,
  MAX_TRACKED_PARSE_KEYS,
  resetMessagesV3ProfilingHooks,
  resetMessagesV3ProfilingState,
  setMessagesV3ProfilingHooks,
  setMessagesV3ProfilingRuntimeOverrideForTests,
  type ParseCacheTraceInput,
  type ParseCacheTraceEvent,
  type RowRenderProfileEvent,
} from '../../src/features/conversation/components/v3/messagesV3ProfilingHooks'

function makeMessageItem({
  threadId = 'thread-1',
  itemId = 'msg-1',
  updatedAt = '2026-04-13T00:00:01Z',
  text = 'First',
  sequence = 1,
}: {
  threadId?: string
  itemId?: string
  updatedAt?: string
  text?: string
  sequence?: number
} = {}): Extract<ConversationItemV3, { kind: 'message' }> {
  return {
    id: itemId,
    kind: 'message',
    threadId,
    turnId: 'turn-1',
    sequence,
    createdAt: updatedAt,
    updatedAt,
    status: 'completed',
    source: 'upstream',
    tone: 'neutral',
    metadata: {},
    role: 'assistant',
    text,
    format: 'markdown',
  }
}

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

function makeParseTraceInput(overrides: Partial<ParseCacheTraceInput> = {}): ParseCacheTraceInput {
  const threadId = overrides.threadId ?? 'thread-1'
  const itemId = overrides.itemId ?? 'msg-1'
  const updatedAt = overrides.updatedAt ?? '2026-04-13T00:00:01Z'
  const mode = overrides.mode ?? 'message_markdown'
  const rendererVersion = overrides.rendererVersion ?? PARSE_CACHE_RENDERER_VERSION
  return {
    source: overrides.source ?? 'messages_v3.profiling_test',
    threadId,
    itemId,
    updatedAt,
    mode,
    rendererVersion,
    key:
      overrides.key ??
      buildParseCacheKey({
        threadId,
        itemId,
        updatedAt,
        mode,
        rendererVersion,
      }),
  }
}

afterEach(() => {
  setMessagesV3ProfilingRuntimeOverrideForTests(null)
  resetMessagesV3ProfilingHooks()
  resetMessagesV3ProfilingState()
})

describe('MessagesV3 profiling hooks', () => {
  it('avoids unchanged-row rerender events when a neighbor row updates', () => {
    setMessagesV3ProfilingRuntimeOverrideForTests({ mode: 'development', envFlagValue: '' })
    const rowEvents: RowRenderProfileEvent[] = []
    setMessagesV3ProfilingHooks({
      onRowRender: (event) => rowEvents.push(event),
    })

    const onResolveUserInput = vi.fn().mockResolvedValue(undefined)
    const firstSnapshot = makeSnapshot({
      items: [
        makeMessageItem({
          itemId: 'msg-1',
          updatedAt: '2026-04-13T00:00:01Z',
          text: 'First',
          sequence: 1,
        }),
        makeMessageItem({
          itemId: 'msg-2',
          updatedAt: '2026-04-13T00:00:02Z',
          text: 'Second',
          sequence: 2,
        }),
      ],
    })
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

    const { rerender } = render(
      <MessagesV3 snapshot={firstSnapshot} isLoading={false} onResolveUserInput={onResolveUserInput} />,
    )
    rerender(<MessagesV3 snapshot={secondSnapshot} isLoading={false} onResolveUserInput={onResolveUserInput} />)

    const msg1Count = rowEvents.filter((event) => event.itemId === 'msg-1').length
    const msg2Count = rowEvents.filter((event) => event.itemId === 'msg-2').length

    expect(msg1Count).toBe(1)
    expect(msg2Count).toBeGreaterThanOrEqual(2)
  })

  it('emits parse trace only when key inputs change at callsites', () => {
    const parseEvents: ParseCacheTraceEvent[] = []
    setMessagesV3ProfilingRuntimeOverrideForTests({ mode: 'development', envFlagValue: '' })
    setMessagesV3ProfilingHooks({
      onParseCacheTrace: (event) => {
        parseEvents.push(event)
      },
    })

    const onResolveUserInput = vi.fn().mockResolvedValue(undefined)
    const firstSnapshot = makeSnapshot({
      items: [
        makeMessageItem({
          itemId: 'msg-1',
          updatedAt: '2026-04-13T00:00:01Z',
          text: 'First',
          sequence: 1,
        }),
        makeMessageItem({
          itemId: 'msg-2',
          updatedAt: '2026-04-13T00:00:02Z',
          text: 'Second',
          sequence: 2,
        }),
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

    expect(parseEvents.filter((event) => event.key === msg1Key)).toHaveLength(1)
    expect(parseEvents.find((event) => event.key === msg1Key)?.hit).toBe(false)
    expect(parseEvents.filter((event) => event.key === msg2InitialKey)).toHaveLength(1)
    expect(parseEvents.find((event) => event.key === msg2InitialKey)?.hit).toBe(false)
    expect(parseEvents.filter((event) => event.key === msg2UpdatedKey)).toHaveLength(1)
    expect(parseEvents.find((event) => event.key === msg2UpdatedKey)?.hit).toBe(false)
  })

  it('is disabled by default (non-test mode + no env flag + no subscriber) and does not accumulate parse state', () => {
    setMessagesV3ProfilingRuntimeOverrideForTests({ mode: 'development', envFlagValue: '' })
    setMessagesV3ProfilingHooks(null)

    const onResolveUserInput = vi.fn().mockResolvedValue(undefined)
    const snapshot = makeSnapshot({
      items: [
        makeMessageItem({
          itemId: 'msg-default-off',
          updatedAt: '2026-04-13T00:10:00Z',
          text: 'Default off',
        }),
      ],
    })

    const { rerender } = render(
      <MessagesV3 snapshot={snapshot} isLoading={false} onResolveUserInput={onResolveUserInput} />,
    )
    rerender(<MessagesV3 snapshot={snapshot} isLoading={false} onResolveUserInput={onResolveUserInput} />)

    const traceInput = makeParseTraceInput({
      threadId: 'thread-1',
      itemId: 'msg-default-off',
      updatedAt: '2026-04-13T00:10:00Z',
    })
    const first = emitParseCacheTrace(traceInput)
    const second = emitParseCacheTrace(traceInput)
    expect(first.hit).toBe(false)
    expect(second.hit).toBe(false)

    const parseEvents: ParseCacheTraceEvent[] = []
    setMessagesV3ProfilingHooks({
      onParseCacheTrace: (event) => parseEvents.push(event),
    })
    const afterEnableFirst = emitParseCacheTrace(traceInput)
    const afterEnableSecond = emitParseCacheTrace(traceInput)
    expect(afterEnableFirst.hit).toBe(false)
    expect(afterEnableSecond.hit).toBe(true)
    expect(parseEvents.map((event) => event.hit)).toEqual([false, true])
  })

  it('emits miss then hit when profiling is enabled via hook subscriber', () => {
    setMessagesV3ProfilingRuntimeOverrideForTests({ mode: 'development', envFlagValue: '' })

    const parseEvents: ParseCacheTraceEvent[] = []
    setMessagesV3ProfilingHooks({
      onParseCacheTrace: (event) => parseEvents.push(event),
    })

    const traceInput = makeParseTraceInput({
      threadId: 'thread-enabled',
      itemId: 'item-enabled',
      updatedAt: '2026-04-13T00:20:00Z',
    })

    emitParseCacheTrace(traceInput)
    emitParseCacheTrace(traceInput)

    expect(parseEvents.map((event) => event.hit)).toEqual([false, true])
  })

  it('enforces bounded parse-key retention with FIFO eviction', () => {
    setMessagesV3ProfilingRuntimeOverrideForTests({ mode: 'development', envFlagValue: '' })
    setMessagesV3ProfilingHooks({
      onParseCacheTrace: () => undefined,
    })

    const oldestTrace = makeParseTraceInput({
      threadId: 'thread-bounded',
      itemId: 'item-0',
      updatedAt: '2026-04-13T01:00:00Z',
    })

    emitParseCacheTrace(oldestTrace)
    for (let index = 1; index < MAX_TRACKED_PARSE_KEYS + 5; index += 1) {
      emitParseCacheTrace(
        makeParseTraceInput({
          threadId: 'thread-bounded',
          itemId: `item-${index}`,
          updatedAt: `2026-04-13T01:00:${String(index).padStart(2, '0')}Z`,
        }),
      )
    }

    const replayOldest = emitParseCacheTrace(oldestTrace)
    expect(replayOldest.hit).toBe(false)

    const newestTrace = makeParseTraceInput({
      threadId: 'thread-bounded',
      itemId: `item-${MAX_TRACKED_PARSE_KEYS + 4}`,
      updatedAt: `2026-04-13T01:00:${String(MAX_TRACKED_PARSE_KEYS + 4).padStart(2, '0')}Z`,
    })
    const replayNewest = emitParseCacheTrace(newestTrace)
    expect(replayNewest.hit).toBe(true)
  })

  it('resets parse-key tracking when MessagesV3 threadId changes', () => {
    setMessagesV3ProfilingRuntimeOverrideForTests({ mode: 'development', envFlagValue: '' })
    setMessagesV3ProfilingHooks({
      onParseCacheTrace: () => undefined,
    })

    const onResolveUserInput = vi.fn().mockResolvedValue(undefined)
    const snapshotA = makeSnapshot({
      threadId: 'thread-A',
      items: [
        makeMessageItem({
          threadId: 'thread-A',
          itemId: 'msg-A',
          updatedAt: '2026-04-13T02:00:00Z',
        }),
      ],
    })
    const snapshotB = makeSnapshot({
      threadId: 'thread-B',
      items: [
        makeMessageItem({
          threadId: 'thread-B',
          itemId: 'msg-B',
          updatedAt: '2026-04-13T02:01:00Z',
        }),
      ],
    })

    const { rerender } = render(
      <MessagesV3 snapshot={snapshotA} isLoading={false} onResolveUserInput={onResolveUserInput} />,
    )

    const threadATrace = makeParseTraceInput({
      threadId: 'thread-A',
      itemId: 'msg-A',
      updatedAt: '2026-04-13T02:00:00Z',
    })
    expect(emitParseCacheTrace(threadATrace).hit).toBe(false)
    expect(emitParseCacheTrace(threadATrace).hit).toBe(true)

    rerender(<MessagesV3 snapshot={snapshotB} isLoading={false} onResolveUserInput={onResolveUserInput} />)

    expect(emitParseCacheTrace(threadATrace).hit).toBe(false)
  })
})
