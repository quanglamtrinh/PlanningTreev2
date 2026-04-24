import { useCallback, useEffect, useRef } from 'react'
import type { MutableRefObject } from 'react'

import type { ThreadCreationPolicy } from '../contracts'
import { useConnectionStore } from '../store/connectionStore'
import { usePendingRequestsStore } from '../store/pendingRequestsStore'
import { useThreadSessionStore } from '../store/threadSessionStore'
import type { SessionEventStreamController } from './sessionEventStreamController'
import type { SessionBootstrapPolicy, SessionRuntimeController } from './sessionRuntimeController'

type RuntimeOwnership = {
  ownerCount: number
  lifecycleGeneration: number
}

type RuntimeLease = {
  lifecycleGeneration: number
  isPrimary: boolean
  released: boolean
}

type RuntimeLeaseBootstrapPolicy = SessionBootstrapPolicy & {
  autoBootstrapOnMount: boolean
  threadCreationPolicy?: ThreadCreationPolicy
}

type UseSessionRuntimeLeaseOptions = {
  bootstrapPolicy: RuntimeLeaseBootstrapPolicy
  runtimeControllerRef: MutableRefObject<SessionRuntimeController | null>
  streamControllerRef: MutableRefObject<SessionEventStreamController | null>
}

const runtimeOwnership: RuntimeOwnership = {
  ownerCount: 0,
  lifecycleGeneration: 0,
}

function getCurrentLifecycleGeneration(): number {
  return runtimeOwnership.lifecycleGeneration
}

function acquireRuntimeLease(): RuntimeLease {
  const isPrimary = runtimeOwnership.ownerCount === 0
  runtimeOwnership.ownerCount += 1
  if (isPrimary) {
    runtimeOwnership.lifecycleGeneration += 1
  }
  return {
    lifecycleGeneration: runtimeOwnership.lifecycleGeneration,
    isPrimary,
    released: false,
  }
}

function releaseRuntimeLease(lease: RuntimeLease): number {
  if (lease.released) {
    return runtimeOwnership.ownerCount
  }

  lease.released = true
  runtimeOwnership.ownerCount = Math.max(0, runtimeOwnership.ownerCount - 1)
  if (runtimeOwnership.ownerCount === 0) {
    runtimeOwnership.lifecycleGeneration += 1
  }
  return runtimeOwnership.ownerCount
}

export function useSessionRuntimeLease({
  bootstrapPolicy,
  runtimeControllerRef,
  streamControllerRef,
}: UseSessionRuntimeLeaseOptions) {
  const leaseRef = useRef<RuntimeLease | null>(null)
  const disposedRef = useRef(false)

  const isCurrentLifecycle = useCallback(() => {
    const lease = leaseRef.current
    if (disposedRef.current || !lease) {
      return false
    }
    return lease.lifecycleGeneration === getCurrentLifecycleGeneration()
  }, [])

  const isPrimaryLifecycleOwner = useCallback(() => {
    return Boolean(leaseRef.current?.isPrimary) && isCurrentLifecycle()
  }, [isCurrentLifecycle])

  useEffect(() => {
    const lease = acquireRuntimeLease()
    leaseRef.current = lease
    disposedRef.current = false

    if (lease.isPrimary && bootstrapPolicy.autoBootstrapOnMount) {
      void runtimeControllerRef.current?.bootstrap({
        autoSelectInitialThread: bootstrapPolicy.autoSelectInitialThread,
        autoCreateThreadWhenEmpty: bootstrapPolicy.autoCreateThreadWhenEmpty,
        threadCreationPolicy: bootstrapPolicy.threadCreationPolicy,
      })
    }

    return () => {
      disposedRef.current = true
      const activeThreadId = useThreadSessionStore.getState().activeThreadId
      streamControllerRef.current?.close(activeThreadId)
      streamControllerRef.current?.dispose()
      runtimeControllerRef.current?.dispose()
      const remainingOwners = releaseRuntimeLease(lease)
      leaseRef.current = null

      if (remainingOwners === 0) {
        usePendingRequestsStore.getState().clear()
        useThreadSessionStore.getState().clear()
        useConnectionStore.getState().reset()
      }
    }
  }, [
    bootstrapPolicy.autoBootstrapOnMount,
    bootstrapPolicy.autoCreateThreadWhenEmpty,
    bootstrapPolicy.autoSelectInitialThread,
    bootstrapPolicy.threadCreationPolicy,
    runtimeControllerRef,
    streamControllerRef,
  ])

  return {
    isCurrentLifecycle,
    isPrimaryLifecycleOwner,
  }
}

export function getSessionFacadeRuntimeOwnershipSnapshot(): RuntimeOwnership {
  return {
    ownerCount: runtimeOwnership.ownerCount,
    lifecycleGeneration: runtimeOwnership.lifecycleGeneration,
  }
}

export function resetSessionFacadeRuntimeOwnershipForTests(): void {
  runtimeOwnership.ownerCount = 0
  runtimeOwnership.lifecycleGeneration = 0
  useThreadSessionStore.getState().clear()
  usePendingRequestsStore.getState().clear()
  useConnectionStore.getState().reset()
}
