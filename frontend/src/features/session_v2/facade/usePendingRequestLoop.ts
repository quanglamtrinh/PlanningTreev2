import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { MutableRefObject } from 'react'

import type { PendingServerRequest, SessionTurn } from '../contracts'
import { usePendingRequestsStore } from '../store/pendingRequestsStore'
import type { SessionEventStreamController } from './sessionEventStreamController'
import type { SessionRuntimeController } from './sessionRuntimeController'

type PendingRequestScope = 'global' | 'activeThread'

type PendingRequestsStoreState = ReturnType<typeof usePendingRequestsStore.getState>

type UsePendingRequestLoopOptions = {
  activeThreadId: string | null
  activeRunningTurn: SessionTurn | null
  queueLength: number
  pendingRequestsStoreState: PendingRequestsStoreState
  pendingRequestScope: PendingRequestScope
  runtimeControllerRef: MutableRefObject<SessionRuntimeController | null>
  streamControllerRef: MutableRefObject<SessionEventStreamController | null>
  isCurrentLifecycle: () => boolean
  isPrimaryLifecycleOwner: () => boolean
}

function resolveActiveRequestId(options: {
  activeRequestId: string | null
  queue: string[]
  pendingById: Record<string, PendingServerRequest>
  activeThreadId: string | null
  pendingRequestScope: PendingRequestScope
}): string | null {
  const { activeRequestId, queue, pendingById, activeThreadId, pendingRequestScope } = options
  const scopedQueue =
    pendingRequestScope === 'activeThread'
      ? queue.filter((requestId) => pendingById[requestId]?.threadId === activeThreadId)
      : queue

  if (activeRequestId && scopedQueue.includes(activeRequestId)) {
    return activeRequestId
  }
  return scopedQueue[0] ?? null
}

export function usePendingRequestLoop({
  activeThreadId,
  activeRunningTurn,
  queueLength,
  pendingRequestsStoreState,
  pendingRequestScope,
  runtimeControllerRef,
  streamControllerRef,
  isCurrentLifecycle,
  isPrimaryLifecycleOwner,
}: UsePendingRequestLoopOptions) {
  const pollTimerRef = useRef<number | null>(null)
  const pollGenerationRef = useRef(0)

  const activeRequest = useMemo(() => {
    const requestId = resolveActiveRequestId({
      activeRequestId: pendingRequestsStoreState.activeRequestId,
      queue: pendingRequestsStoreState.queue,
      pendingById: pendingRequestsStoreState.pendingById,
      activeThreadId,
      pendingRequestScope,
    })
    if (!requestId) {
      return null
    }
    return pendingRequestsStoreState.pendingById[requestId] ?? null
  }, [
    activeThreadId,
    pendingRequestScope,
    pendingRequestsStoreState.activeRequestId,
    pendingRequestsStoreState.pendingById,
    pendingRequestsStoreState.queue,
  ])

  const clearPendingPollTimer = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const stopPendingRequestLoop = useCallback(() => {
    pollGenerationRef.current += 1
    clearPendingPollTimer()
  }, [clearPendingPollTimer])

  const pollPendingRequests = useCallback(async () => {
    if (!isCurrentLifecycle()) {
      return
    }
    const runtimeController = runtimeControllerRef.current
    if (!runtimeController) {
      return
    }
    await runtimeController.pollPendingRequests()
  }, [isCurrentLifecycle, runtimeControllerRef])

  const schedulePendingPoll = useCallback(() => {
    if (!isCurrentLifecycle()) {
      return
    }

    pollGenerationRef.current += 1
    const generation = pollGenerationRef.current

    clearPendingPollTimer()
    const intervalMs = activeRunningTurn || queueLength > 0 ? 400 : 2000
    pollTimerRef.current = window.setTimeout(async () => {
      if (!isCurrentLifecycle() || pollGenerationRef.current !== generation) {
        return
      }
      await pollPendingRequests()
      if (!isCurrentLifecycle() || pollGenerationRef.current !== generation) {
        return
      }
      schedulePendingPoll()
    }, intervalMs)
  }, [activeRunningTurn, clearPendingPollTimer, isCurrentLifecycle, pollPendingRequests, queueLength])

  useEffect(() => {
    return () => {
      stopPendingRequestLoop()
    }
  }, [stopPendingRequestLoop])

  useEffect(() => {
    if (!activeThreadId || !isPrimaryLifecycleOwner()) {
      return
    }

    streamControllerRef.current?.open(activeThreadId)
    void pollPendingRequests()
    schedulePendingPoll()

    return () => {
      stopPendingRequestLoop()
      streamControllerRef.current?.close(activeThreadId)
    }
  }, [
    activeThreadId,
    isPrimaryLifecycleOwner,
    pollPendingRequests,
    schedulePendingPoll,
    stopPendingRequestLoop,
    streamControllerRef,
  ])

  useEffect(() => {
    const resolvedActiveRequestId = activeRequest?.requestId ?? null
    if (pendingRequestsStoreState.activeRequestId === resolvedActiveRequestId) {
      return
    }
    usePendingRequestsStore.getState().setActiveRequest(resolvedActiveRequestId)
  }, [activeRequest?.requestId, pendingRequestsStoreState.activeRequestId])

  useEffect(() => {
    if (!activeRequest) {
      return
    }

    const current = pendingRequestsStoreState.pendingById[activeRequest.requestId]
    if (!current) {
      usePendingRequestsStore.getState().markResolved(activeRequest.requestId)
      return
    }

    if (current.status === 'resolved') {
      usePendingRequestsStore.getState().markResolved(current.requestId)
      return
    }

    if (current.status === 'rejected' || current.status === 'expired') {
      usePendingRequestsStore.getState().markRejected(current.requestId)
    }
  }, [activeRequest, pendingRequestsStoreState.pendingById])

  return {
    activeRequest,
    stopPendingRequestLoop,
  }
}
