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

    await runSelectingCommand(async () => {
      await runtimeControllerRef.current?.selectThread(threadId)
    })
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
