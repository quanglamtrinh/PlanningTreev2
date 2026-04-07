import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../../api/client'
import type { LocalUsageSnapshot } from '../../api/types'

export const DEFAULT_LOCAL_USAGE_DAYS = 30
export const LOCAL_USAGE_POLL_INTERVAL_MS = 5 * 60 * 1000

export type UseLocalUsageSnapshotResult = {
  snapshot: LocalUsageSnapshot | null
  isLoading: boolean
  error: string | null
}

type RefreshReason = 'initial' | 'poll'

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

export function useLocalUsageSnapshot(): UseLocalUsageSnapshotResult {
  const [snapshot, setSnapshot] = useState<LocalUsageSnapshot | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const snapshotRef = useRef<LocalUsageSnapshot | null>(null)
  const requestGenerationRef = useRef(0)
  const isMountedRef = useRef(false)

  const requestSnapshot = useCallback(async (reason: RefreshReason) => {
    const requestGeneration = ++requestGenerationRef.current
    const hasSnapshot = snapshotRef.current !== null

    if (reason === 'initial' || !hasSnapshot) {
      setIsLoading(true)
    }

    try {
      const nextSnapshot = await api.getLocalUsageSnapshot(DEFAULT_LOCAL_USAGE_DAYS)
      if (!isMountedRef.current || requestGeneration !== requestGenerationRef.current) {
        return
      }

      snapshotRef.current = nextSnapshot
      setSnapshot(nextSnapshot)
      setError(null)
    } catch (requestError) {
      if (!isMountedRef.current || requestGeneration !== requestGenerationRef.current) {
        return
      }
      setError(toErrorMessage(requestError))
    } finally {
      if (!isMountedRef.current || requestGeneration !== requestGenerationRef.current) {
        return
      }
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    isMountedRef.current = true
    void requestSnapshot('initial')
    const intervalId = window.setInterval(() => {
      void requestSnapshot('poll')
    }, LOCAL_USAGE_POLL_INTERVAL_MS)

    return () => {
      isMountedRef.current = false
      window.clearInterval(intervalId)
    }
  }, [requestSnapshot])

  return {
    snapshot,
    isLoading,
    error,
  }
}
