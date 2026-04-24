import { useCallback, useEffect, useMemo, useRef } from 'react'
import type { MutableRefObject } from 'react'

import type { PendingServerRequest } from '../contracts'
import { usePendingRequestsStore } from '../store/pendingRequestsStore'
import type { SessionEventStreamController } from './sessionEventStreamController'
import type { SessionRuntimeController } from './sessionRuntimeController'

type PendingRequestScope = 'global' | 'activeThread'

type PendingRequestsStoreState = ReturnType<typeof usePendingRequestsStore.getState>

type UsePendingRequestLoopOptions = {
  activeThreadId: string | null
  streamConnected: boolean
  pendingRequestsStoreState: PendingRequestsStoreState
  pendingRequestScope: PendingRequestScope
  runtimeControllerRef: MutableRefObject<SessionRuntimeController | null>
  streamControllerRef: MutableRefObject<SessionEventStreamController | null>
  isCurrentLifecycle: () => boolean
  isPrimaryLifecycleOwner: () => boolean
}

const CONNECTED_RECONCILE_POLL_MS = 30_000
const DISCONNECTED_FALLBACK_POLL_MS = 1_500

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
  streamConnected,
  pendingRequestsStoreState,
  pendingRequestScope,
  runtimeControllerRef,
  streamControllerRef,
  isCurrentLifecycle,
  isPrimaryLifecycleOwner,
}: UsePendingRequestLoopOptions) {
  const pollTimerRef = useRef<number | null>(null)

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

  const stopPendingRequestLoop = useCallback(() => {
    if (pollTimerRef.current !== null) {
      window.clearTimeout(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }, [])

  const pollPendingRequests = useCallback(async (options?: { surfaceErrors?: boolean }) => {
    if (!isCurrentLifecycle()) {
      return
    }
    const runtimeController = runtimeControllerRef.current
    if (!runtimeController) {
      return
    }
    await runtimeController.pollPendingRequests(options)
  }, [isCurrentLifecycle, runtimeControllerRef])

  useEffect(() => {
    if (!activeThreadId || !isPrimaryLifecycleOwner()) {
      return
    }

    streamControllerRef.current?.open(activeThreadId)
    void pollPendingRequests({ surfaceErrors: false })

    return () => {
      stopPendingRequestLoop()
      streamControllerRef.current?.close(activeThreadId)
    }
  }, [
    activeThreadId,
    isPrimaryLifecycleOwner,
    pollPendingRequests,
    stopPendingRequestLoop,
    streamControllerRef,
  ])

  useEffect(() => {
    if (!activeThreadId || !isPrimaryLifecycleOwner()) {
      stopPendingRequestLoop()
      return
    }

    let cancelled = false
    const intervalMs = streamConnected ? CONNECTED_RECONCILE_POLL_MS : DISCONNECTED_FALLBACK_POLL_MS

    const scheduleNextPoll = () => {
      stopPendingRequestLoop()
      pollTimerRef.current = window.setTimeout(async () => {
        if (cancelled || !isCurrentLifecycle()) {
          return
        }

        await pollPendingRequests({ surfaceErrors: !streamConnected })
        if (cancelled || !isCurrentLifecycle()) {
          return
        }
        scheduleNextPoll()
      }, intervalMs)
    }

    scheduleNextPoll()

    return () => {
      cancelled = true
      stopPendingRequestLoop()
    }
  }, [
    activeThreadId,
    isCurrentLifecycle,
    isPrimaryLifecycleOwner,
    pollPendingRequests,
    stopPendingRequestLoop,
    streamConnected,
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
