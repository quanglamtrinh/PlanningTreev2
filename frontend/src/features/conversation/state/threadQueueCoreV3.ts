export type QueueLane = 'execution' | 'ask_planning'

export type QueueEntryStatus = 'queued' | 'requires_confirmation' | 'sending' | 'failed'

export type QueueCoreEntry<TContext> = {
  entryId: string
  text: string
  idempotencyKey: string
  createdAtMs: number
  enqueueContext: TContext
  status: QueueEntryStatus
  attemptCount: number
  lastError: string | null
}

export type NextEligibleEntryOptions = {
  manualEntryId?: string | null
}

export function normalizeQueueEntryStatus(value: unknown): QueueEntryStatus {
  const normalized = String(value ?? '').trim()
  if (
    normalized === 'queued' ||
    normalized === 'requires_confirmation' ||
    normalized === 'sending' ||
    normalized === 'failed'
  ) {
    return normalized
  }
  return 'queued'
}

export function queueHasSending<TContext>(entries: QueueCoreEntry<TContext>[]): boolean {
  return entries.some((entry) => entry.status === 'sending')
}

export function enqueueQueueEntry<TContext>(
  lane: QueueLane,
  entries: QueueCoreEntry<TContext>[],
  entry: QueueCoreEntry<TContext>,
  maxItems: number,
): QueueCoreEntry<TContext>[] {
  void lane
  const cappedEntries = entries.slice(0, Math.max(0, Math.floor(maxItems)))
  return [...cappedEntries, entry].slice(-Math.max(0, Math.floor(maxItems)))
}

export function removeQueueEntry<TContext>(
  lane: QueueLane,
  entries: QueueCoreEntry<TContext>[],
  entryId: string,
): QueueCoreEntry<TContext>[] {
  void lane
  const normalizedId = String(entryId ?? '').trim()
  if (!normalizedId) {
    return entries
  }
  return entries.filter((entry) => entry.entryId !== normalizedId)
}

export function reorderQueueEntries<TContext>(
  lane: QueueLane,
  entries: QueueCoreEntry<TContext>[],
  fromIndex: number,
  toIndex: number,
): QueueCoreEntry<TContext>[] {
  void lane
  if (entries.length <= 1) {
    return entries
  }
  const from = Math.max(0, Math.min(entries.length - 1, Math.floor(fromIndex)))
  const to = Math.max(0, Math.min(entries.length - 1, Math.floor(toIndex)))
  if (from === to) {
    return entries
  }
  const next = [...entries]
  const [moved] = next.splice(from, 1)
  next.splice(to, 0, moved)
  return next
}

export function markQueueEntrySending<TContext>(
  lane: QueueLane,
  entries: QueueCoreEntry<TContext>[],
  entryId: string,
): QueueCoreEntry<TContext>[] {
  void lane
  const normalizedId = String(entryId ?? '').trim()
  if (!normalizedId) {
    return entries
  }
  if (queueHasSending(entries)) {
    const alreadySending = entries.some(
      (entry) => entry.entryId === normalizedId && entry.status === 'sending',
    )
    if (!alreadySending) {
      return entries
    }
  }
  return entries.map((entry) =>
    entry.entryId === normalizedId
      ? {
          ...entry,
          status: 'sending' as const,
          lastError: null,
        }
      : entry,
  )
}

export function markQueueEntryFailed<TContext>(
  lane: QueueLane,
  entries: QueueCoreEntry<TContext>[],
  entryId: string,
  error: string,
): QueueCoreEntry<TContext>[] {
  void lane
  const normalizedId = String(entryId ?? '').trim()
  if (!normalizedId) {
    return entries
  }
  return entries.map((entry) =>
    entry.entryId === normalizedId
      ? {
          ...entry,
          status: 'failed' as const,
          attemptCount: entry.attemptCount + 1,
          lastError: error,
        }
      : entry,
  )
}

export function markQueueEntryRequiresConfirmation<TContext>(
  lane: QueueLane,
  entries: QueueCoreEntry<TContext>[],
  entryId: string,
): QueueCoreEntry<TContext>[] {
  void lane
  const normalizedId = String(entryId ?? '').trim()
  if (!normalizedId) {
    return entries
  }
  return entries.map((entry) =>
    entry.entryId === normalizedId
      ? {
          ...entry,
          status: 'requires_confirmation' as const,
          lastError: null,
        }
      : entry,
  )
}

export function markQueueEntryConfirmed<TContext>(
  lane: QueueLane,
  entries: QueueCoreEntry<TContext>[],
  entryId: string,
  options: {
    nowMs: number
    enqueueContext: TContext
  },
): QueueCoreEntry<TContext>[] {
  void lane
  const normalizedId = String(entryId ?? '').trim()
  if (!normalizedId) {
    return entries
  }
  const nowMs = options.nowMs
  const enqueueContext = options.enqueueContext
  return entries.map((entry) =>
    entry.entryId === normalizedId
      ? {
          ...entry,
          status: 'queued' as const,
          createdAtMs: nowMs,
          enqueueContext,
          lastError: null,
        }
      : entry,
  )
}

export function retryQueueEntry<TContext>(
  lane: QueueLane,
  entries: QueueCoreEntry<TContext>[],
  entryId: string,
): QueueCoreEntry<TContext>[] {
  void lane
  const normalizedId = String(entryId ?? '').trim()
  if (!normalizedId) {
    return entries
  }
  return entries.map((entry) =>
    entry.entryId === normalizedId && entry.status === 'failed'
      ? {
          ...entry,
          status: 'queued' as const,
          lastError: null,
        }
      : entry,
  )
}

export function nextEligibleQueueEntry<TContext>(
  lane: QueueLane,
  entries: QueueCoreEntry<TContext>[],
  options: NextEligibleEntryOptions = {},
): QueueCoreEntry<TContext> | null {
  void lane
  if (queueHasSending(entries)) {
    return null
  }
  const manualEntryId = String(options.manualEntryId ?? '').trim()
  if (manualEntryId) {
    const manualEntry = entries.find((entry) => entry.entryId === manualEntryId) ?? null
    if (!manualEntry || manualEntry.status === 'sending') {
      return null
    }
    return manualEntry
  }
  return entries.find((entry) => entry.status === 'queued') ?? null
}

// AQ2 frozen surface aliases (lane-neutral core API contract).
export function enqueue<TContext>(
  lane: QueueLane,
  entry: QueueCoreEntry<TContext>,
  state: QueueCoreEntry<TContext>[],
  maxItems: number,
): QueueCoreEntry<TContext>[] {
  return enqueueQueueEntry(lane, state, entry, maxItems)
}

export function remove<TContext>(
  lane: QueueLane,
  entryId: string,
  state: QueueCoreEntry<TContext>[],
): QueueCoreEntry<TContext>[] {
  return removeQueueEntry(lane, state, entryId)
}

export function reorder<TContext>(
  lane: QueueLane,
  fromIndex: number,
  toIndex: number,
  state: QueueCoreEntry<TContext>[],
): QueueCoreEntry<TContext>[] {
  return reorderQueueEntries(lane, state, fromIndex, toIndex)
}

export function markSending<TContext>(
  lane: QueueLane,
  entryId: string,
  state: QueueCoreEntry<TContext>[],
): QueueCoreEntry<TContext>[] {
  return markQueueEntrySending(lane, state, entryId)
}

export function markFailed<TContext>(
  lane: QueueLane,
  entryId: string,
  error: string,
  state: QueueCoreEntry<TContext>[],
): QueueCoreEntry<TContext>[] {
  return markQueueEntryFailed(lane, state, entryId, error)
}

export function markConfirmed<TContext>(
  lane: QueueLane,
  entryId: string,
  state: QueueCoreEntry<TContext>[],
  options: {
    nowMs: number
    enqueueContext: TContext
  },
): QueueCoreEntry<TContext>[] {
  return markQueueEntryConfirmed(lane, state, entryId, options)
}

export function nextEligibleEntry<TContext>(
  lane: QueueLane,
  state: QueueCoreEntry<TContext>[],
  options: NextEligibleEntryOptions = {},
): QueueCoreEntry<TContext> | null {
  return nextEligibleQueueEntry(lane, state, options)
}
