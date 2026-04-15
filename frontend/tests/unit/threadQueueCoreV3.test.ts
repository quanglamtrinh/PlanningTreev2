import { describe, expect, it } from 'vitest'

import {
  enqueue,
  enqueueQueueEntry,
  markConfirmed,
  markFailed,
  markSending,
  markQueueEntryConfirmed,
  markQueueEntryFailed,
  markQueueEntryRequiresConfirmation,
  markQueueEntrySending,
  nextEligibleEntry,
  nextEligibleQueueEntry,
  queueHasSending,
  remove,
  removeQueueEntry,
  reorder,
  reorderQueueEntries,
  retryQueueEntry,
  type QueueCoreEntry,
} from '../../src/features/conversation/state/threadQueueCoreV3'

type QueueContext = {
  marker: string
}

function makeEntry(
  entryId: string,
  status: QueueCoreEntry<QueueContext>['status'] = 'queued',
  createdAtMs = 1_000,
): QueueCoreEntry<QueueContext> {
  return {
    entryId,
    text: `text-${entryId}`,
    idempotencyKey: `idem-${entryId}`,
    createdAtMs,
    enqueueContext: {
      marker: 'ctx-a',
    },
    status,
    attemptCount: 0,
    lastError: null,
  }
}

function summarize(entries: QueueCoreEntry<QueueContext>[]): string[] {
  return entries.map((entry) => `${entry.entryId}:${entry.status}:${entry.attemptCount}:${entry.lastError ?? '-'}`)
}

describe('threadQueueCoreV3', () => {
  it('enqueues deterministically with a fixed cap', () => {
    let queue: QueueCoreEntry<QueueContext>[] = []
    queue = enqueueQueueEntry('execution', queue, makeEntry('a'), 2)
    queue = enqueueQueueEntry('execution', queue, makeEntry('b'), 2)
    queue = enqueueQueueEntry('execution', queue, makeEntry('c'), 2)

    expect(queue.map((entry) => entry.entryId)).toEqual(['b', 'c'])
  })

  it('removes and reorders entries while preserving deterministic order', () => {
    const initial = [makeEntry('a'), makeEntry('b'), makeEntry('c')]
    const removed = removeQueueEntry('execution', initial, 'b')
    expect(removed.map((entry) => entry.entryId)).toEqual(['a', 'c'])

    const reordered = reorderQueueEntries('execution', removed, 1, 0)
    expect(reordered.map((entry) => entry.entryId)).toEqual(['c', 'a'])
  })

  it('enforces single-flight sending per lane and blocks nextEligible while sending exists', () => {
    const initial = [makeEntry('a'), makeEntry('b')]
    const sendingA = markQueueEntrySending('execution', initial, 'a')
    expect(sendingA.map((entry) => entry.status)).toEqual(['sending', 'queued'])
    expect(queueHasSending(sendingA)).toBe(true)

    const blockedSecondSend = markQueueEntrySending('execution', sendingA, 'b')
    expect(blockedSecondSend).toEqual(sendingA)
    expect(nextEligibleQueueEntry('execution', blockedSecondSend)).toBeNull()
  })

  it('supports requires_confirmation -> confirmed -> failed -> retry transitions', () => {
    let queue = [makeEntry('a')]
    queue = markQueueEntryRequiresConfirmation('execution', queue, 'a')
    expect(queue[0].status).toBe('requires_confirmation')

    queue = markQueueEntryConfirmed('execution', queue, 'a', {
      nowMs: 2_000,
      enqueueContext: { marker: 'ctx-b' },
    })
    expect(queue[0].status).toBe('queued')
    expect(queue[0].createdAtMs).toBe(2_000)
    expect(queue[0].enqueueContext).toEqual({ marker: 'ctx-b' })

    queue = markQueueEntryFailed('execution', queue, 'a', 'network')
    expect(queue[0].status).toBe('failed')
    expect(queue[0].attemptCount).toBe(1)
    expect(queue[0].lastError).toBe('network')

    queue = retryQueueEntry('execution', queue, 'a')
    expect(queue[0].status).toBe('queued')
    expect(queue[0].attemptCount).toBe(1)
    expect(queue[0].lastError).toBeNull()
  })

  it('keeps manual next-eligible deterministic and lane-neutral', () => {
    const queue = [makeEntry('a', 'requires_confirmation'), makeEntry('b', 'queued')]
    expect(nextEligibleQueueEntry('execution', queue)?.entryId).toBe('b')
    expect(nextEligibleQueueEntry('execution', queue, { manualEntryId: 'a' })?.entryId).toBe('a')
    expect(nextEligibleQueueEntry('ask_planning', queue, { manualEntryId: 'a' })?.entryId).toBe('a')
  })

  it('replays the same transition sequence without divergence', () => {
    const runScenario = (): string[] => {
      let queue: QueueCoreEntry<QueueContext>[] = [makeEntry('a'), makeEntry('b', 'failed')]
      const transitions: string[] = []

      queue = enqueueQueueEntry('execution', queue, makeEntry('c'), 8)
      transitions.push(JSON.stringify(summarize(queue)))

      queue = reorderQueueEntries('execution', queue, 2, 0)
      transitions.push(JSON.stringify(summarize(queue)))

      const next = nextEligibleQueueEntry('execution', queue)
      queue = markQueueEntrySending('execution', queue, next?.entryId ?? '')
      transitions.push(JSON.stringify(summarize(queue)))

      queue = markQueueEntryFailed('execution', queue, 'c', 'timeout')
      transitions.push(JSON.stringify(summarize(queue)))

      queue = retryQueueEntry('execution', queue, 'c')
      transitions.push(JSON.stringify(summarize(queue)))

      queue = markQueueEntryConfirmed('execution', queue, 'c', {
        nowMs: 3_000,
        enqueueContext: { marker: 'ctx-confirmed' },
      })
      transitions.push(JSON.stringify(summarize(queue)))

      queue = removeQueueEntry('execution', queue, 'b')
      transitions.push(JSON.stringify(summarize(queue)))

      return transitions
    }

    const baseline = runScenario()
    for (let index = 0; index < 25; index += 1) {
      expect(runScenario()).toEqual(baseline)
    }
  })

  it('supports AQ2 frozen alias surface without changing transition behavior', () => {
    const queue0 = [makeEntry('a'), makeEntry('b')]
    const queue1 = enqueue('execution', makeEntry('c'), queue0, 8)
    const queue2 = reorder('execution', 2, 0, queue1)
    const queue3 = markSending('execution', 'c', queue2)
    const queue4 = markFailed('execution', 'c', 'error', queue3)
    const queue5 = markConfirmed('execution', 'c', queue4, {
      nowMs: 4_000,
      enqueueContext: { marker: 'ctx-c' },
    })
    const queue6 = remove('execution', 'b', queue5)

    expect(nextEligibleEntry('execution', queue6)?.entryId).toBe('c')
    expect(queue6.map((entry) => entry.entryId)).toEqual(['c', 'a'])
  })
})
