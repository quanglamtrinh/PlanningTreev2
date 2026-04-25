import { useCallback, useRef, useState } from 'react'
import type { MutableRefObject } from 'react'

import type { ThreadCreationPolicy } from '../contracts'
import { useThreadSessionStore } from '../store/threadSessionStore'
import type { SessionEventStreamController } from './sessionEventStreamController'
import type { SessionRuntimeController } from './sessionRuntimeController'

type UseSessionSelectionStateOptions = {
  runtimeControllerRef: MutableRefObject<SessionRuntimeController | null>
  streamControllerRef: MutableRefObject<SessionEventStreamController | null>
  stopPendingRequestLoop: () => void
}

function buildThreadDataSnapshot(threadId: string) {
  const state = useThreadSessionStore.getState()
  const thread = state.threadsById[threadId] ?? null
  const turns = state.turnsByThread[threadId] ?? []
  const itemCount = turns.reduce((count, turn) => {
    return count + (state.itemsByTurn[`${threadId}:${turn.id}`]?.length ?? 0)
  }, 0)
  return {
    requestedThreadId: threadId,
    resolvedThreadId: thread?.id ?? null,
    threadExists: Boolean(thread),
    status: state.threadStatus[threadId]?.type ?? thread?.status?.type ?? null,
    model: thread?.model ?? null,
    modelProvider: thread?.modelProvider ?? null,
    turnsCount: turns.length,
    turnIds: turns.slice(-5).map((turn) => turn.id),
    itemsCount: itemCount,
    lastEventSeq: state.lastEventSeqByThread[threadId] ?? null,
    streamConnected: Boolean(state.streamState.connectedByThread[threadId]),
  }
}

function emitSelectionCorrelation(payload: Record<string, unknown>): void {
  if (typeof window === 'undefined') {
    return
  }
  console.info('[session-v2-select] correlation', payload)
  window.dispatchEvent(new CustomEvent('session-v2-correlation', { detail: payload }))
}

export function useSessionSelectionState({
  runtimeControllerRef,
  streamControllerRef,
  stopPendingRequestLoop,
}: UseSessionSelectionStateOptions) {
  const [isSelectingThread, setIsSelectingThread] = useState(false)
  const selectingOperationCountRef = useRef(0)

  const runSelectingCommand = useCallback(async (run: () => Promise<void>) => {
    selectingOperationCountRef.current += 1
    setIsSelectingThread(true)
    try {
      await run()
    } finally {
      selectingOperationCountRef.current = Math.max(0, selectingOperationCountRef.current - 1)
      if (selectingOperationCountRef.current === 0) {
        setIsSelectingThread(false)
      }
    }
  }, [])

  const selectThread = useCallback(async (threadId: string | null) => {
    if (threadId === null) {
      stopPendingRequestLoop()
      const activeThreadId = useThreadSessionStore.getState().activeThreadId
      streamControllerRef.current?.close(activeThreadId)
    }

    emitSelectionCorrelation({
      type: 'select_thread_requested',
      targetThreadId: threadId,
      currentThreadId: useThreadSessionStore.getState().activeThreadId,
    })
    try {
      await runSelectingCommand(async () => {
        await runtimeControllerRef.current?.selectThread(threadId)

        if (threadId === null) {
          return
        }
        const resolvedActiveThreadId = useThreadSessionStore.getState().activeThreadId
        if (resolvedActiveThreadId !== threadId) {
          emitSelectionCorrelation({
            type: 'select_thread_open_skipped',
            targetThreadId: threadId,
            activeThreadId: resolvedActiveThreadId,
            activeThreadSnapshot: resolvedActiveThreadId
              ? buildThreadDataSnapshot(resolvedActiveThreadId)
              : null,
          })
          return
        }
        streamControllerRef.current?.open(threadId)
        emitSelectionCorrelation({
          type: 'select_thread_snapshot',
          targetThreadId: threadId,
          activeThreadId: resolvedActiveThreadId,
          snapshot: buildThreadDataSnapshot(threadId),
        })
      })
      emitSelectionCorrelation({
        type: 'select_thread_applied',
        targetThreadId: threadId,
        activeThreadId: useThreadSessionStore.getState().activeThreadId,
      })
    } catch (error) {
      emitSelectionCorrelation({
        type: 'select_thread_failed',
        targetThreadId: threadId,
        activeThreadId: useThreadSessionStore.getState().activeThreadId,
        error: error instanceof Error ? error.message : String(error),
      })
      throw error
    }
  }, [runtimeControllerRef, runSelectingCommand, stopPendingRequestLoop, streamControllerRef])

  const createThread = useCallback(async (policy?: ThreadCreationPolicy) => {
    await runSelectingCommand(async () => {
      await runtimeControllerRef.current?.createThread(policy)
    })
  }, [runtimeControllerRef, runSelectingCommand])

  const forkThread = useCallback(async (threadId: string) => {
    await runSelectingCommand(async () => {
      await runtimeControllerRef.current?.forkThread(threadId)
    })
  }, [runtimeControllerRef, runSelectingCommand])

  return {
    isSelectingThread,
    selectThread,
    createThread,
    forkThread,
  }
}
