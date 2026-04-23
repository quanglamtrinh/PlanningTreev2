import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'

import { createSessionEventStreamController } from '../../src/features/session_v2/facade/sessionEventStreamController'
import type { SessionEventEnvelope, SessionNotificationMethod } from '../../src/features/session_v2/contracts'

class FakeEventSource {
  onopen: ((this: EventSource, event: Event) => unknown) | null = null
  onerror: ((this: EventSource, event: Event) => unknown) | null = null

  private readonly listeners = new Map<string, Set<EventListener>>()
  private closed = false

  addEventListener(type: string, listener: EventListener): void {
    const set = this.listeners.get(type) ?? new Set<EventListener>()
    set.add(listener)
    this.listeners.set(type, set)
  }

  close(): void {
    this.closed = true
  }

  isClosed(): boolean {
    return this.closed
  }

  emitOpen(): void {
    this.onopen?.call(this as unknown as EventSource, new Event('open'))
  }

  emitError(): void {
    this.onerror?.call(this as unknown as EventSource, new Event('error'))
  }

  emit(method: SessionNotificationMethod, envelope: SessionEventEnvelope): void {
    const listeners = this.listeners.get(method)
    if (!listeners) {
      return
    }

    const event = {
      data: JSON.stringify(envelope),
    } as MessageEvent

    for (const listener of listeners) {
      listener.call(this, event as unknown as Event)
    }
  }
}

function envelope(partial: Partial<SessionEventEnvelope>): SessionEventEnvelope {
  return {
    schemaVersion: 1,
    eventId: 'thread-1:1',
    eventSeq: 1,
    tier: 'tier0',
    method: 'item/agentMessage/delta',
    threadId: 'thread-1',
    turnId: 'turn-1',
    occurredAtMs: 1,
    replayable: true,
    snapshotVersion: null,
    source: 'journal',
    params: {
      itemId: 'item-1',
      delta: 'hello',
    },
    ...partial,
  }
}

describe('sessionEventStreamController', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('opens stream, marks connected, and closes cleanly', () => {
    const sources: FakeEventSource[] = []
    const markConnected = vi.fn()
    const markDisconnected = vi.fn()

    const controller = createSessionEventStreamController({
      openEventSource: () => {
        const source = new FakeEventSource()
        sources.push(source)
        return source as unknown as EventSource
      },
      applyEventsBatch: vi.fn(),
      markStreamConnected: markConnected,
      markStreamDisconnected: markDisconnected,
      markStreamReconnect: vi.fn(),
      clearGapDetected: vi.fn(),
      getLastEventId: () => null,
      getGapDetected: () => false,
      onRuntimeError: vi.fn(),
    })

    controller.open('thread-1')
    expect(sources).toHaveLength(1)

    sources[0].emitOpen()
    expect(markConnected).toHaveBeenCalledWith('thread-1')

    controller.close('thread-1')
    expect(sources[0].isClosed()).toBe(true)
    expect(markDisconnected).toHaveBeenCalledWith('thread-1')
  })

  it('retries reconnect after stream error', async () => {
    const sources: FakeEventSource[] = []
    const markReconnect = vi.fn()
    const runtimeError = vi.fn()

    const controller = createSessionEventStreamController({
      openEventSource: () => {
        const source = new FakeEventSource()
        sources.push(source)
        return source as unknown as EventSource
      },
      applyEventsBatch: vi.fn(),
      markStreamConnected: vi.fn(),
      markStreamDisconnected: vi.fn(),
      markStreamReconnect: markReconnect,
      clearGapDetected: vi.fn(),
      getLastEventId: () => null,
      getGapDetected: () => false,
      onRuntimeError: runtimeError,
    })

    controller.open('thread-1')
    expect(sources).toHaveLength(1)

    sources[0].emitError()
    expect(markReconnect).toHaveBeenCalledWith('thread-1')
    expect(runtimeError).toHaveBeenCalledWith('Session stream disconnected. Reconnecting...')

    await vi.advanceTimersByTimeAsync(1000)
    expect(sources).toHaveLength(2)
  })

  it('handles openEventSource failure and schedules reconnect with runtime error', async () => {
    const openEventSource = vi.fn()
      .mockImplementationOnce(() => {
        throw new Error('boom open')
      })
      .mockImplementation(() => new FakeEventSource() as unknown as EventSource)
    const runtimeError = vi.fn()

    const controller = createSessionEventStreamController({
      openEventSource,
      applyEventsBatch: vi.fn(),
      markStreamConnected: vi.fn(),
      markStreamDisconnected: vi.fn(),
      markStreamReconnect: vi.fn(),
      clearGapDetected: vi.fn(),
      getLastEventId: () => null,
      getGapDetected: () => false,
      onRuntimeError: runtimeError,
    })

    controller.open('thread-1')

    expect(runtimeError).toHaveBeenCalledWith('boom open')
    expect(openEventSource).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(1000)
    expect(openEventSource).toHaveBeenCalledTimes(2)
  })

  it('batches delta events and flushes queue on fallback timer', async () => {
    const sources: FakeEventSource[] = []
    const applyEventsBatch = vi.fn()

    const controller = createSessionEventStreamController({
      openEventSource: () => {
        const source = new FakeEventSource()
        sources.push(source)
        return source as unknown as EventSource
      },
      applyEventsBatch,
      markStreamConnected: vi.fn(),
      markStreamDisconnected: vi.fn(),
      markStreamReconnect: vi.fn(),
      clearGapDetected: vi.fn(),
      getLastEventId: () => null,
      getGapDetected: () => false,
      onRuntimeError: vi.fn(),
    })

    controller.open('thread-1')

    sources[0].emit(
      'item/agentMessage/delta',
      envelope({ eventId: 'thread-1:10', eventSeq: 10, params: { itemId: 'item-1', delta: 'A' } }),
    )
    sources[0].emit(
      'item/agentMessage/delta',
      envelope({ eventId: 'thread-1:11', eventSeq: 11, params: { itemId: 'item-1', delta: 'B' } }),
    )

    await vi.advanceTimersByTimeAsync(20)

    expect(applyEventsBatch).toHaveBeenCalledTimes(1)
    const [[batch]] = applyEventsBatch.mock.calls
    expect(batch).toHaveLength(2)
    expect(batch[0].eventId).toBe('thread-1:10')
    expect(batch[1].eventId).toBe('thread-1:11')
  })

  it('force flushes terminal envelopes and restarts on gap detection', async () => {
    const sources: FakeEventSource[] = []
    const clearGapDetected = vi.fn()
    const openEventSource = vi.fn(() => {
      const source = new FakeEventSource()
      sources.push(source)
      return source as unknown as EventSource
    })

    let gapDetected = false
    const applyEventsBatch = vi.fn(() => {
      gapDetected = true
    })

    const controller = createSessionEventStreamController({
      openEventSource,
      applyEventsBatch,
      markStreamConnected: vi.fn(),
      markStreamDisconnected: vi.fn(),
      markStreamReconnect: vi.fn(),
      clearGapDetected,
      getLastEventId: () => null,
      getGapDetected: () => gapDetected,
      onRuntimeError: vi.fn(),
    })

    controller.open('thread-1')

    sources[0].emit(
      'turn/completed',
      envelope({
        method: 'turn/completed',
        turnId: 'turn-1',
        eventId: 'thread-1:20',
        eventSeq: 20,
        params: { turn: { id: 'turn-1', status: 'completed' } },
      }),
    )

    await vi.advanceTimersByTimeAsync(0)

    expect(applyEventsBatch).toHaveBeenCalledTimes(1)
    expect(openEventSource).toHaveBeenCalledTimes(2)
    expect(clearGapDetected).toHaveBeenCalled()
  })

  it('cleans reconnect timer on dispose', async () => {
    const sources: FakeEventSource[] = []
    const openEventSource = vi.fn(() => {
      const source = new FakeEventSource()
      sources.push(source)
      return source as unknown as EventSource
    })

    const controller = createSessionEventStreamController({
      openEventSource,
      applyEventsBatch: vi.fn(),
      markStreamConnected: vi.fn(),
      markStreamDisconnected: vi.fn(),
      markStreamReconnect: vi.fn(),
      clearGapDetected: vi.fn(),
      getLastEventId: () => null,
      getGapDetected: () => false,
      onRuntimeError: vi.fn(),
    })

    controller.open('thread-1')
    expect(sources).toHaveLength(1)

    sources[0].emitError()
    controller.dispose()

    await vi.advanceTimersByTimeAsync(2000)
    expect(openEventSource).toHaveBeenCalledTimes(1)
  })
})
