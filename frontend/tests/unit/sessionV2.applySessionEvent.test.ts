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
})

