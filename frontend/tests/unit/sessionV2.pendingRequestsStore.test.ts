import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  PendingServerRequest,
  ServerRequestMethod,
  SessionEventEnvelope,
  SessionNotificationMethod,
} from '../../src/features/session_v2/contracts'
import { usePendingRequestsStore } from '../../src/features/session_v2/store/pendingRequestsStore'

function makeRequest(overrides: Partial<PendingServerRequest> & { requestId: string }): PendingServerRequest {
  return {
    requestId: overrides.requestId,
    method: overrides.method ?? 'item/tool/requestUserInput',
    threadId: overrides.threadId ?? 'thread-1',
    turnId: overrides.turnId ?? 'turn-1',
    itemId: overrides.itemId ?? 'item-1',
    status: overrides.status ?? 'pending',
    createdAtMs: overrides.createdAtMs ?? 1,
    submittedAtMs: overrides.submittedAtMs ?? null,
    resolvedAtMs: overrides.resolvedAtMs ?? null,
    payload: overrides.payload ?? {},
    inactiveByReconcile: overrides.inactiveByReconcile,
    reconciledAtMs: overrides.reconciledAtMs,
  }
}

function requestEvent(
  method: SessionNotificationMethod,
  request: PendingServerRequest,
  eventSeq: number,
): SessionEventEnvelope {
  return {
    schemaVersion: 1,
    eventId: `${request.threadId}:${eventSeq}`,
    eventSeq,
    tier: 'tier0',
    method,
    threadId: request.threadId,
    turnId: request.turnId,
    occurredAtMs: eventSeq,
    replayable: true,
    snapshotVersion: null,
    source: 'journal',
    params: { request },
  }
}

describe('pendingRequestsStore', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00.000Z'))
    usePendingRequestsStore.getState().clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('applies created, updated, and resolved events through one derived queue path', () => {
    const first = makeRequest({ requestId: 'req-1', createdAtMs: 2 })
    const second = makeRequest({ requestId: 'req-2', createdAtMs: 1 })

    usePendingRequestsStore.getState().applyRequestEventsBatch([
      requestEvent('serverRequest/created', first, 1),
      requestEvent('serverRequest/created', second, 2),
    ])

    expect(usePendingRequestsStore.getState().queue).toEqual(['req-2', 'req-1'])
    expect(usePendingRequestsStore.getState().activeRequestId).toBe('req-2')

    usePendingRequestsStore.getState().setActiveRequest('req-1')
    usePendingRequestsStore.getState().applyRequestEvent(
      requestEvent('serverRequest/updated', { ...first, status: 'submitted', submittedAtMs: 10 }, 3),
    )

    expect(usePendingRequestsStore.getState().pendingById['req-1']?.status).toBe('submitted')
    expect(usePendingRequestsStore.getState().queue).toEqual(['req-2'])
    expect(usePendingRequestsStore.getState().activeRequestId).toBe('req-2')

    usePendingRequestsStore.getState().applyRequestEvent(
      requestEvent('serverRequest/resolved', { ...first, status: 'resolved', submittedAtMs: 10, resolvedAtMs: 20 }, 4),
    )

    expect(usePendingRequestsStore.getState().pendingById['req-1']?.status).toBe('resolved')
    expect(usePendingRequestsStore.getState().queue).toEqual(['req-2'])
  })

  it('reconciles missing active rows as inactive without faking terminal status', () => {
    const pending = makeRequest({ requestId: 'req-1' })

    usePendingRequestsStore.getState().hydrateFromServer([pending])
    expect(usePendingRequestsStore.getState().queue).toEqual(['req-1'])

    usePendingRequestsStore.getState().reconcileFromServer([])

    const reconciled = usePendingRequestsStore.getState().pendingById['req-1']
    expect(reconciled?.status).toBe('pending')
    expect(reconciled?.inactiveByReconcile).toBe(true)
    expect(reconciled?.reconciledAtMs).toBe(Date.now())
    expect(usePendingRequestsStore.getState().queue).toEqual([])
    expect(usePendingRequestsStore.getState().activeRequestId).toBeNull()
    expect(usePendingRequestsStore.getState().lastPollAtMs).toBe(Date.now())

    usePendingRequestsStore.getState().applyRequestEvent(
      requestEvent('serverRequest/updated', { ...pending, payload: { prompt: 'again' } }, 5),
    )

    const revived = usePendingRequestsStore.getState().pendingById['req-1']
    expect(revived?.status).toBe('pending')
    expect(revived?.inactiveByReconcile).toBe(false)
    expect(revived?.reconciledAtMs).toBeUndefined()
    expect(usePendingRequestsStore.getState().queue).toEqual(['req-1'])
  })

  it('keeps optimistic submitted state when an older created event arrives late', () => {
    const pending = makeRequest({ requestId: 'req-1' })

    usePendingRequestsStore.getState().applyRequestEvent(requestEvent('serverRequest/created', pending, 1))
    usePendingRequestsStore.getState().markSubmitted('req-1')

    expect(usePendingRequestsStore.getState().pendingById['req-1']?.status).toBe('submitted')
    expect(usePendingRequestsStore.getState().queue).toEqual([])

    usePendingRequestsStore.getState().applyRequestEvent(requestEvent('serverRequest/created', pending, 2))

    expect(usePendingRequestsStore.getState().pendingById['req-1']?.status).toBe('submitted')
    expect(usePendingRequestsStore.getState().queue).toEqual([])
  })

  it('ignores malformed request event payloads', () => {
    usePendingRequestsStore.getState().applyRequestEvent({
      ...requestEvent(
        'serverRequest/created',
        makeRequest({ requestId: 'req-valid', method: 'item/fileChange/requestApproval' as ServerRequestMethod }),
        1,
      ),
      params: { request: { requestId: '', threadId: 'thread-1' } },
    })

    expect(usePendingRequestsStore.getState().queue).toEqual([])
    expect(usePendingRequestsStore.getState().pendingById).toEqual({})
  })
})
