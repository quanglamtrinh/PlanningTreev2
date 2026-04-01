import { useEffect } from 'react'
import { appendAuthToken, buildProjectEventsUrlV2 } from '../../../api/client'
import { useDetailStateStore } from '../../../stores/detail-state-store'
import { useWorkflowStateStoreV2 } from './workflowStateStoreV2'
import { parseWorkflowEventEnvelope } from './threadEventRouter'

const RECONNECT_DELAY_MS = 1000

export function useWorkflowEventBridge(
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
          // Keep the event bridge alive even if workflow refresh fails.
        }
      })()
    }

    const refreshDetailState = () => {
      void (async () => {
        try {
          await useDetailStateStore.getState().refreshExecutionState(projectId, nodeId)
        } catch {
          // Ignore detail refresh failures; the next workflow event will retry.
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
      const url = appendAuthToken(buildProjectEventsUrlV2(projectId))
      eventSource = new EventSource(url)

      eventSource.onmessage = (message) => {
        if (disposed) {
          return
        }
        try {
          const event = parseWorkflowEventEnvelope(message.data)
          if (event.projectId !== projectId || event.nodeId !== nodeId) {
            return
          }
          if (event.type === 'node.workflow.updated') {
            refreshWorkflowState()
            return
          }
          if (event.type === 'node.detail.invalidate') {
            refreshWorkflowState()
            refreshDetailState()
          }
        } catch {
          // Ignore malformed workflow events and keep the bridge alive.
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
