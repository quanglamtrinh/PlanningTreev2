import { describe, expect, it } from 'vitest'

import { parseThreadEventEnvelopeV3 } from '../../src/features/conversation/state/threadEventRouter'

describe('threadEventRouter', () => {
  it('parses canonical business envelope and exposes threadId', () => {
    const frame = parseThreadEventEnvelopeV3(
      JSON.stringify({
        schema_version: 1,
        event_id: '20',
        event_type: 'thread.snapshot.v3',
        thread_id: 'thread-1',
        turn_id: null,
        snapshot_version: 2,
        occurred_at_ms: Date.parse('2026-04-01T00:01:00Z'),
        eventId: '20',
        channel: 'thread',
        projectId: 'project-1',
        nodeId: 'node-1',
        threadRole: 'execution',
        occurredAt: '2026-04-01T00:01:00Z',
        snapshotVersion: 2,
        type: 'thread.snapshot.v3',
        payload: {
          snapshot: {
            projectId: 'project-1',
            nodeId: 'node-1',
            threadId: 'thread-1',
            threadRole: 'execution',
            activeTurnId: null,
            processingState: 'idle',
            snapshotVersion: 2,
            createdAt: '2026-04-01T00:00:00Z',
            updatedAt: '2026-04-01T00:01:00Z',
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
          },
        },
      }),
    )

    expect(frame.kind).toBe('business')
    if (frame.kind !== 'business') {
      return
    }
    expect(frame.legacyFallbackUsed).toBe(false)
    expect(frame.event.threadId).toBe('thread-1')
    expect(frame.event.eventId).toBe('20')
  })

  it('parses legacy business fallback envelope and derives threadId', () => {
    const frame = parseThreadEventEnvelopeV3(
      JSON.stringify({
        eventId: '21',
        channel: 'thread',
        projectId: 'project-1',
        nodeId: 'node-1',
        threadRole: 'execution',
        occurredAt: '2026-04-01T00:01:00Z',
        snapshotVersion: 2,
        type: 'conversation.item.upsert.v3',
        payload: {
          item: {
            id: 'msg-1',
            kind: 'message',
            threadId: 'thread-legacy',
            turnId: null,
            sequence: 1,
            createdAt: '2026-04-01T00:01:00Z',
            updatedAt: '2026-04-01T00:01:00Z',
            status: 'completed',
            source: 'upstream',
            tone: 'neutral',
            metadata: {},
            role: 'assistant',
            text: 'legacy payload',
            format: 'markdown',
          },
        },
      }),
    )

    expect(frame.kind).toBe('business')
    if (frame.kind !== 'business') {
      return
    }
    expect(frame.legacyFallbackUsed).toBe(true)
    expect(frame.event.threadId).toBe('thread-legacy')
    expect(frame.event.eventId).toBe('21')
  })
})
