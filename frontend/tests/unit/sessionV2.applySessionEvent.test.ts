import { describe, expect, it } from 'vitest'

import { applySessionEvent, type SessionProjectionState } from '../../src/features/session_v2/state/applySessionEvent'
import type { SessionEventEnvelope } from '../../src/features/session_v2/contracts'

function baseState(): SessionProjectionState {
  return {
    threadsById: {},
    threadOrder: [],
    turnsByThread: {},
    itemsByTurn: {},
    lastEventSeqByThread: {},
    lastEventIdByThread: {},
    gapDetectedByThread: {},
    threadStatus: {},
    tokenUsageByThread: {},
  }
}

function event(partial: Partial<SessionEventEnvelope>): SessionEventEnvelope {
  return {
    schemaVersion: 1,
    eventId: 'thread-1:1',
    eventSeq: 1,
    tier: 'tier0',
    method: 'thread/started',
    threadId: 'thread-1',
    turnId: null,
    occurredAtMs: 1,
    replayable: true,
    snapshotVersion: null,
    source: 'journal',
    params: {},
    ...partial,
  }
}

describe('applySessionEvent', () => {
  it('deduplicates older events by eventSeq', () => {
    const initial = applySessionEvent(
      baseState(),
      event({
        eventId: 'thread-1:5',
        eventSeq: 5,
        method: 'thread/status/changed',
        params: { status: { type: 'active', activeFlags: ['inProgress'] } },
      }),
    )

    const duplicate = applySessionEvent(
      initial,
      event({
        eventId: 'thread-1:4',
        eventSeq: 4,
        method: 'thread/status/changed',
        params: { status: { type: 'idle' } },
      }),
    )

    expect(duplicate).toBe(initial)
    expect(duplicate.threadStatus['thread-1']).toEqual({ type: 'active', activeFlags: ['inProgress'] })
  })

  it('flags gap detection when eventSeq skips', () => {
    const afterFirst = applySessionEvent(baseState(), event({ eventId: 'thread-1:1', eventSeq: 1 }))
    const withGap = applySessionEvent(
      afterFirst,
      event({
        eventId: 'thread-1:4',
        eventSeq: 4,
        method: 'item/agentMessage/delta',
        turnId: 'turn-1',
        params: { itemId: 'item-1', textDelta: 'hello' },
      }),
    )

    expect(withGap.gapDetectedByThread['thread-1']).toBe(true)
    expect(withGap.lastEventSeqByThread['thread-1']).toBe(4)
  })

  it('does not bump thread ordering timestamp for status-only events', () => {
    const initial = baseState()
    initial.threadsById['thread-1'] = {
      id: 'thread-1',
      name: 'Thread 1',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      ephemeral: false,
      archived: false,
      status: { type: 'idle' },
      createdAt: 1,
      updatedAt: 10,
      turns: [],
    }
    initial.threadOrder = ['thread-1']
    initial.threadStatus['thread-1'] = { type: 'idle' }

    const next = applySessionEvent(
      initial,
      event({
        eventId: 'thread-1:10',
        eventSeq: 10,
        method: 'thread/status/changed',
        occurredAtMs: 30,
        params: { status: { type: 'active', activeFlags: ['connected'] } },
      }),
    )

    expect(next.threadStatus['thread-1']).toEqual({ type: 'active', activeFlags: ['connected'] })
    expect(next.threadsById['thread-1']?.updatedAt).toBe(10)
  })

  it('bumps thread ordering timestamp for real item activity', () => {
    const initial = baseState()
    initial.threadsById['thread-1'] = {
      id: 'thread-1',
      name: 'Thread 1',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      ephemeral: false,
      archived: false,
      status: { type: 'idle' },
      createdAt: 1,
      updatedAt: 10,
      turns: [],
    }
    initial.threadOrder = ['thread-1']

    const next = applySessionEvent(
      initial,
      event({
        eventId: 'thread-1:11',
        eventSeq: 11,
        method: 'item/started',
        turnId: 'turn-1',
        occurredAtMs: 30,
        params: {
          item: {
            id: 'item-1',
            kind: 'userMessage',
            status: 'completed',
            text: 'hello',
          },
        },
      }),
    )

    expect(next.threadsById['thread-1']?.updatedAt).toBe(30)
  })

  it('upserts item lifecycle and completion state', () => {
    const started = applySessionEvent(
      baseState(),
      event({
        eventId: 'thread-1:10',
        eventSeq: 10,
        method: 'item/started',
        turnId: 'turn-1',
        params: {
          item: {
            id: 'item-1',
            kind: 'agentMessage',
            status: 'inProgress',
            text: 'draft',
          },
        },
      }),
    )
    const completed = applySessionEvent(
      started,
      event({
        eventId: 'thread-1:11',
        eventSeq: 11,
        method: 'item/completed',
        turnId: 'turn-1',
        params: {
          item: {
            id: 'item-1',
            kind: 'agentMessage',
            status: 'completed',
            text: 'final',
          },
        },
      }),
    )

    const list = completed.itemsByTurn['thread-1:turn-1']
    expect(list).toHaveLength(1)
    expect(list[0].status).toBe('completed')
    expect(list[0].payload.text).toBe('final')
  })

  it('preserves unknown native item kind without coercing to agent message', () => {
    const next = applySessionEvent(
      baseState(),
      event({
        eventId: 'thread-1:12',
        eventSeq: 12,
        method: 'item/started',
        turnId: 'turn-1',
        params: {
          item: {
            id: 'item-native-unknown',
            kind: 'browserScreenshot',
            status: 'completed',
            imageUrl: 'https://example.test/screenshot.png',
          },
        },
      }),
    )

    const list = next.itemsByTurn['thread-1:turn-1']
    expect(list).toHaveLength(1)
    expect(list[0].kind).toBe('browserScreenshot')
    expect(list[0].normalizedKind).toBeNull()
    expect(list[0].rawItem?.kind).toBe('browserScreenshot')
    expect(list[0].payload.imageUrl).toBe('https://example.test/screenshot.png')
  })

  it('ignores replayed delta for already completed item', () => {
    const completed = applySessionEvent(
      baseState(),
      event({
        eventId: 'thread-1:20',
        eventSeq: 20,
        method: 'item/completed',
        turnId: 'turn-1',
        params: {
          item: {
            id: 'item-1',
            kind: 'agentMessage',
            status: 'completed',
            text: 'final answer',
          },
        },
      }),
    )

    const replayDelta = applySessionEvent(
      completed,
      event({
        eventId: 'thread-1:21',
        eventSeq: 21,
        method: 'item/agentMessage/delta',
        turnId: 'turn-1',
        params: {
          itemId: 'item-1',
          delta: ' duplicated',
        },
      }),
    )

    const list = replayDelta.itemsByTurn['thread-1:turn-1']
    expect(list).toHaveLength(1)
    expect(list[0].status).toBe('completed')
    expect(list[0].payload.text).toBe('final answer')
  })

  it('reconciles hydrated fallback item with replayed real item id', () => {
    const preloaded = baseState()
    preloaded.itemsByTurn['thread-1:turn-1'] = [
      {
        id: 'turn-1:item-0',
        threadId: 'thread-1',
        turnId: 'turn-1',
        kind: 'userMessage',
        status: 'completed',
        createdAtMs: 1,
        updatedAtMs: 1,
        payload: {
          type: 'userMessage',
          text: 'same prompt',
        },
      },
    ]

    const replayed = applySessionEvent(
      preloaded,
      event({
        eventId: 'thread-1:30',
        eventSeq: 30,
        method: 'item/completed',
        turnId: 'turn-1',
        params: {
          item: {
            id: 'item-user-1',
            kind: 'userMessage',
            status: 'completed',
            text: 'same prompt',
            type: 'userMessage',
          },
        },
      }),
    )

    const list = replayed.itemsByTurn['thread-1:turn-1']
    expect(list).toHaveLength(1)
    expect(list[0].id).toBe('item-user-1')
    expect(list[0].payload.text).toBe('same prompt')
  })

  it('updates thread name + activity timestamp from thread/name/updated', () => {
    const initial = baseState()
    initial.threadsById['thread-1'] = {
      id: 'thread-1',
      name: 'Before',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      ephemeral: false,
      archived: false,
      status: { type: 'idle' },
      createdAt: 1,
      updatedAt: 10,
      turns: [],
    }
    initial.threadOrder = ['thread-1']

    const next = applySessionEvent(
      initial,
      event({
        eventId: 'thread-1:100',
        eventSeq: 100,
        method: 'thread/name/updated',
        occurredAtMs: 50,
        params: { name: 'After' },
      }),
    )

    expect(next.threadsById['thread-1']?.name).toBe('After')
    expect(next.threadsById['thread-1']?.updatedAt).toBe(50)
  })

  it('handles thread archive/unarchive events and keeps activity timestamp monotonic', () => {
    const initial = baseState()
    initial.threadsById['thread-1'] = {
      id: 'thread-1',
      name: 'Thread',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      ephemeral: false,
      archived: false,
      status: { type: 'idle' },
      createdAt: 1,
      updatedAt: 10,
      turns: [],
    }
    initial.threadOrder = ['thread-1']

    const archived = applySessionEvent(
      initial,
      event({
        eventId: 'thread-1:101',
        eventSeq: 101,
        method: 'thread/archived',
        occurredAtMs: 40,
        params: {},
      }),
    )
    const unarchived = applySessionEvent(
      archived,
      event({
        eventId: 'thread-1:102',
        eventSeq: 102,
        method: 'thread/unarchived',
        occurredAtMs: 60,
        params: {},
      }),
    )

    expect(archived.threadsById['thread-1']?.archived).toBe(true)
    expect(unarchived.threadsById['thread-1']?.archived).toBe(false)
    expect(unarchived.threadsById['thread-1']?.updatedAt).toBe(60)
  })

  it('marks thread activity on serverRequest/resolved', () => {
    const initial = baseState()
    initial.threadsById['thread-1'] = {
      id: 'thread-1',
      name: 'Thread',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      ephemeral: false,
      archived: false,
      status: { type: 'idle' },
      createdAt: 1,
      updatedAt: 10,
      turns: [],
    }
    initial.threadOrder = ['thread-1']

    const next = applySessionEvent(
      initial,
      event({
        eventId: 'thread-1:103',
        eventSeq: 103,
        method: 'serverRequest/resolved',
        occurredAtMs: 70,
        params: { requestId: 'request-1' },
      }),
    )

    expect(next.threadsById['thread-1']?.updatedAt).toBe(70)
  })

  it('creates and deduplicates synthetic error item id when turnId exists', () => {
    const initial = baseState()
    initial.threadsById['thread-1'] = {
      id: 'thread-1',
      name: 'Thread',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      ephemeral: false,
      archived: false,
      status: { type: 'idle' },
      createdAt: 1,
      updatedAt: 10,
      turns: [],
    }
    initial.threadOrder = ['thread-1']
    initial.turnsByThread['thread-1'] = [
      {
        id: 'turn-1',
        threadId: 'thread-1',
        status: 'inProgress',
        lastCodexStatus: 'inProgress',
        startedAtMs: 5,
        completedAtMs: null,
        items: [],
        error: null,
      },
    ]

    const first = applySessionEvent(
      initial,
      event({
        eventId: 'thread-1:104',
        eventSeq: 104,
        method: 'error',
        turnId: 'turn-1',
        occurredAtMs: 80,
        params: {
          itemId: 'item-error-1',
          error: { code: 'ERR_INTERNAL', message: 'first' },
        },
      }),
    )
    const second = applySessionEvent(
      first,
      event({
        eventId: 'thread-1:105',
        eventSeq: 105,
        method: 'error',
        turnId: 'turn-1',
        occurredAtMs: 90,
        params: {
          itemId: 'item-error-1',
          error: { code: 'ERR_INTERNAL', message: 'second' },
        },
      }),
    )

    const items = second.itemsByTurn['thread-1:turn-1']
    expect(items).toHaveLength(1)
    expect(items[0].id).toBe('item-error-1')
    expect(items[0].kind).toBe('error')
    expect(items[0].status).toBe('failed')
    expect(items[0].payload.message).toBe('second')
  })

  it('does not create turn item for error event without turnId', () => {
    const initial = baseState()
    initial.threadsById['thread-1'] = {
      id: 'thread-1',
      name: 'Thread',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      ephemeral: false,
      archived: false,
      status: { type: 'idle' },
      createdAt: 1,
      updatedAt: 10,
      turns: [],
    }
    initial.threadOrder = ['thread-1']

    const next = applySessionEvent(
      initial,
      event({
        eventId: 'thread-1:106',
        eventSeq: 106,
        method: 'error',
        turnId: null,
        occurredAtMs: 95,
        params: {
          requestId: 'request-only',
          error: { code: 'ERR_INTERNAL', message: 'request-level failure' },
        },
      }),
    )

    expect(next.itemsByTurn['thread-1:turn-1']).toBeUndefined()
    expect(next.threadsById['thread-1']?.updatedAt).toBe(95)
  })
})

