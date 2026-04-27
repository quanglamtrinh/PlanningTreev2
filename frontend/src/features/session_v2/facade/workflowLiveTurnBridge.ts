import type { SessionTurn } from '../contracts'
import { useThreadSessionStore } from '../store/threadSessionStore'

export type WorkflowStreamCursor = {
  threadId: string
  lastEventSeq: number | null
  lastEventId: string | null
} | null

export type PrimeWorkflowTurnOptions = {
  actionKind: string
  targetLane: string
  threadId: string | null
  turnId: string | null
  projectId?: string | null
  nodeId?: string | null
  preActionCursor?: WorkflowStreamCursor
  selectThread?: (threadId: string) => Promise<void> | void
}

function emitWorkflowTurnCorrelation(payload: Record<string, unknown>): void {
  if (typeof window === 'undefined') {
    return
  }
  console.info('[session-v2-path] correlation', payload)
  window.dispatchEvent(new CustomEvent('session-v2-correlation', { detail: payload }))
}

function normalizeNonEmpty(value: string | null | undefined): string | null {
  const normalized = typeof value === 'string' ? value.trim() : ''
  return normalized || null
}

export function captureWorkflowStreamCursor(threadId: string | null | undefined): WorkflowStreamCursor {
  const normalizedThreadId = normalizeNonEmpty(threadId)
  if (!normalizedThreadId) {
    return null
  }
  const state = useThreadSessionStore.getState()
  return {
    threadId: normalizedThreadId,
    lastEventSeq: state.lastEventSeqByThread[normalizedThreadId] ?? null,
    lastEventId: state.lastEventIdByThread[normalizedThreadId] ?? null,
  }
}

function restorePreActionCursor(threadId: string, cursor: WorkflowStreamCursor | undefined): void {
  if (!cursor || cursor.threadId !== threadId) {
    return
  }
  const hasCursor =
    (typeof cursor.lastEventSeq === 'number' && Number.isFinite(cursor.lastEventSeq) && cursor.lastEventSeq > 0) ||
    (typeof cursor.lastEventId === 'string' && cursor.lastEventId.trim() !== '')
  if (!hasCursor) {
    return
  }
  useThreadSessionStore
    .getState()
    .setReplayCursor(threadId, Math.max(0, cursor.lastEventSeq ?? 0), cursor.lastEventId ?? null)
}

function buildPrimedTurn(threadId: string, turnId: string): SessionTurn {
  const now = Date.now()
  return {
    id: turnId,
    threadId,
    status: 'inProgress',
    lastCodexStatus: 'inProgress',
    startedAtMs: now,
    completedAtMs: null,
    items: [],
    error: null,
    metadata: { primedByWorkflowAction: true },
  }
}

export async function primeAndSelectWorkflowTurn(options: PrimeWorkflowTurnOptions): Promise<void> {
  const threadId = normalizeNonEmpty(options.threadId)
  const turnId = normalizeNonEmpty(options.turnId)
  if (!threadId) {
    return
  }

  restorePreActionCursor(threadId, options.preActionCursor)

  let alreadyPresent = false
  if (turnId) {
    const store = useThreadSessionStore.getState()
    const turns = store.turnsByThread[threadId] ?? []
    alreadyPresent = turns.some((turn) => turn.id === turnId)
    if (!alreadyPresent) {
      store.setThreadTurns(threadId, [buildPrimedTurn(threadId, turnId)], { mode: 'merge' })
    }
  }

  emitWorkflowTurnCorrelation({
    type: turnId
      ? alreadyPresent
        ? 'workflow_action_turn_present'
        : 'workflow_action_turn_primed'
      : 'workflow_action_thread_selected',
    projectId: options.projectId ?? null,
    nodeId: options.nodeId ?? null,
    lane: options.targetLane,
    action: options.actionKind,
    threadId,
    turnId,
    preActionCursorEventId: options.preActionCursor?.lastEventId ?? null,
    turnsCount: (useThreadSessionStore.getState().turnsByThread[threadId] ?? []).length,
  })

  if (options.selectThread) {
    await options.selectThread(threadId)
    return
  }
  useThreadSessionStore.getState().setActiveThreadId(threadId)
}
