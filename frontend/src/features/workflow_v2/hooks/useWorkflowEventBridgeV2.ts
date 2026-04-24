import { useEffect } from 'react'

import { openWorkflowEventsStreamV2, parseWorkflowEventV2 } from '../api/client'
import { useWorkflowStateStoreV2 } from '../store/workflowStateStoreV2'

const RECONNECT_DELAY_MS = 1000

export function useWorkflowEventBridgeV2(
  projectId: string | null | undefined,
  nodeId: string | null | undefined,
  enabled: boolean,
) {
  useEffect(() => {
    if (!enabled || !projectId || !nodeId) {
      return
    }

    let disposed = false
    let eventSource: EventSource | null = null
    let reconnectTimer: ReturnType<typeof globalThis.setTimeout> | null = null

    const refreshWorkflowState = () => {
      void (async () => {
        try {
          await useWorkflowStateStoreV2.getState().loadWorkflowState(projectId, nodeId)
        } catch {
          // Keep the bridge alive; later workflow events retry the refresh.
        }
      })()
    }

    const closeEventSource = () => {
      if (eventSource) {
        eventSource.close()
        eventSource = null
      }
    }

    const clearReconnectTimer = () => {
      if (reconnectTimer !== null) {
        globalThis.clearTimeout(reconnectTimer)
        reconnectTimer = null
      }
    }

    const connect = () => {
      closeEventSource()
      eventSource = openWorkflowEventsStreamV2(projectId)

      eventSource.onmessage = (message) => {
        if (disposed) {
          return
        }
        try {
          const event = parseWorkflowEventV2(message.data)
          if (event.projectId !== projectId || event.nodeId !== nodeId) {
            return
          }
          if (event.type === 'workflow/state_changed' || event.type === 'workflow/context_stale') {
            refreshWorkflowState()
          }
        } catch {
          // Ignore malformed or irrelevant workflow events and keep listening.
        }
      }

      eventSource.onerror = () => {
        if (disposed) {
          return
        }
        closeEventSource()
        clearReconnectTimer()
        reconnectTimer = globalThis.setTimeout(() => {
          reconnectTimer = null
          if (!disposed) {
            connect()
          }
        }, RECONNECT_DELAY_MS)
      }
    }

    connect()

    return () => {
      disposed = true
      clearReconnectTimer()
      closeEventSource()
    }
  }, [enabled, nodeId, projectId])
}
