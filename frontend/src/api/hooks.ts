import { useEffect } from 'react'

import { api } from './client'
import type { PlanningEvent, SplitMode } from './types'
import { useProjectStore } from '../stores/project-store'

const CANONICAL_SPLIT_MODES = new Set<SplitMode>([
  'workflow',
  'simplify_workflow',
  'phase_breakdown',
  'agent_breakdown',
])

function isCanonicalSplitMode(value: unknown): value is SplitMode {
  return typeof value === 'string' && CANONICAL_SPLIT_MODES.has(value as SplitMode)
}

export function useEffectOnce(effect: () => void | (() => void)) {
  useEffect(effect, [])
}

export function usePlanningEventStream(projectId: string | null, nodeId: string | null) {
  useEffect(() => {
    const store = useProjectStore.getState()
    if (!projectId || !nodeId) {
      store.clearPlanningState()
      return () => {
        useProjectStore.getState().setPlanningConnectionStatus('disconnected')
      }
    }

    const resolvedProjectId = projectId
    const resolvedNodeId = nodeId
    let disposed = false
    let streamOpen = false
    let hasConnectedOnce = false
    let isResyncing = true
    const eventSource = new EventSource(api.planningEventsUrl(resolvedProjectId, resolvedNodeId))

    async function loadHistory(connectionStatus: 'connecting' | 'reconnecting') {
      isResyncing = true
      useProjectStore.getState().setPlanningConnectionStatus(connectionStatus)
      try {
        await useProjectStore.getState().loadPlanningHistory(resolvedProjectId, resolvedNodeId)
        if (!disposed && streamOpen) {
          useProjectStore.getState().setPlanningConnectionStatus('connected')
        }
      } catch {
        if (!disposed) {
          useProjectStore.getState().setPlanningConnectionStatus('disconnected')
        }
      } finally {
        isResyncing = false
      }
    }

    void loadHistory('connecting')

    eventSource.onopen = () => {
      if (disposed) {
        return
      }
      streamOpen = true
      if (hasConnectedOnce) {
        void loadHistory('reconnecting')
        return
      }
      hasConnectedOnce = true
      if (!isResyncing) {
        useProjectStore.getState().setPlanningConnectionStatus('connected')
      }
    }

    eventSource.onmessage = (message) => {
      if (disposed) {
        return
      }
      try {
        const event = JSON.parse(message.data) as PlanningEvent
        if (event.type === 'planning_turn_started' && !isCanonicalSplitMode(event.mode)) {
          return
        }
        useProjectStore.getState().applyPlanningEvent(resolvedProjectId, resolvedNodeId, event)
      } catch {
        return
      }
    }

    eventSource.onerror = () => {
      if (disposed) {
        return
      }
      streamOpen = false
      isResyncing = true
      useProjectStore.getState().setPlanningConnectionStatus('reconnecting')
    }

    return () => {
      disposed = true
      eventSource.close()
      useProjectStore.getState().clearPlanningState()
    }
  }, [nodeId, projectId])
}
