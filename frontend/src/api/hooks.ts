import { useEffect } from 'react'

import { api } from './client'
import type { AgentEvent, AskEvent, PlanningEvent, SplitMode } from './types'
import { useAskStore } from '../stores/ask-store'
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

export function useAskSidecarStream(projectId: string | null, nodeId: string | null) {
  useEffect(() => {
    const store = useAskStore.getState()
    if (!projectId || !nodeId) {
      store.clearSidecar()
      return undefined
    }

    const resolvedProjectId = projectId
    const resolvedNodeId = nodeId
    let disposed = false
    let hasConnectedOnce = false
    let isResyncing = true
    let lastEventSeq = 0
    let bufferedEvents: AskEvent[] = []
    const eventSource = new EventSource(api.askSidecarEventsUrl(resolvedProjectId, resolvedNodeId))

    function applyEvent(event: AskEvent) {
      if (event.event_seq <= lastEventSeq) {
        return
      }
      lastEventSeq = event.event_seq
      useAskStore.getState().applyAskEvent(event)
    }

    function flushBufferedEvents() {
      bufferedEvents
        .sort((left, right) => left.event_seq - right.event_seq)
        .forEach((event) => applyEvent(event))
      bufferedEvents = []
    }

    async function loadSidecar() {
      isResyncing = true
      bufferedEvents = []
      try {
        await useAskStore.getState().loadSidecar(resolvedProjectId, resolvedNodeId)
        if (disposed) {
          return
        }
        lastEventSeq = useAskStore.getState().sidecar?.eventSeq ?? 0
        flushBufferedEvents()
      } catch {
        return
      } finally {
        isResyncing = false
      }
    }

    void loadSidecar()

    eventSource.onopen = () => {
      if (disposed) {
        return
      }
      if (hasConnectedOnce) {
        void loadSidecar()
        return
      }
      hasConnectedOnce = true
    }

    eventSource.onmessage = (message) => {
      if (disposed) {
        return
      }
      try {
        const event = JSON.parse(message.data) as AskEvent
        if (isResyncing) {
          bufferedEvents.push(event)
          return
        }
        applyEvent(event)
      } catch {
        return
      }
    }

    eventSource.onerror = () => {
      if (disposed) {
        return
      }
      isResyncing = true
    }

    return () => {
      disposed = true
      eventSource.close()
      useAskStore.getState().clearSidecar()
    }
  }, [nodeId, projectId])
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

export function useAgentEventStream(projectId: string | null, nodeId: string | null) {
  useEffect(() => {
    const store = useProjectStore.getState()
    if (!projectId || !nodeId) {
      store.clearAgentState()
      return () => {
        useProjectStore.getState().setAgentConnectionStatus('disconnected')
      }
    }

    const resolvedProjectId = projectId
    const resolvedNodeId = nodeId
    let disposed = false
    let streamOpen = false
    let hasConnectedOnce = false
    let isResyncing = true
    let lastEventSeq = 0
    let bufferedEvents: AgentEvent[] = []
    const eventSource = new EventSource(api.agentEventsUrl(resolvedProjectId, resolvedNodeId))

    function applyEvent(event: AgentEvent) {
      if (event.event_seq <= lastEventSeq) {
        return
      }
      lastEventSeq = event.event_seq
      useProjectStore.getState().applyAgentEvent(resolvedProjectId, resolvedNodeId, event)
    }

    function flushBufferedEvents() {
      bufferedEvents
        .sort((left, right) => left.event_seq - right.event_seq)
        .forEach((event) => applyEvent(event))
      bufferedEvents = []
    }

    async function resyncNode(connectionStatus: 'connecting' | 'reconnecting') {
      isResyncing = true
      bufferedEvents = []
      useProjectStore.getState().setAgentConnectionStatus(connectionStatus)
      try {
        await useProjectStore.getState().resyncNodeArtifacts(resolvedNodeId)
        if (disposed) {
          return
        }
        flushBufferedEvents()
        if (streamOpen) {
          useProjectStore.getState().setAgentConnectionStatus('connected')
        }
      } catch {
        if (!disposed) {
          useProjectStore.getState().setAgentConnectionStatus('disconnected')
        }
      } finally {
        isResyncing = false
      }
    }

    void resyncNode('connecting')

    eventSource.onopen = () => {
      if (disposed) {
        return
      }
      streamOpen = true
      if (hasConnectedOnce) {
        void resyncNode('reconnecting')
        return
      }
      hasConnectedOnce = true
      if (!isResyncing) {
        useProjectStore.getState().setAgentConnectionStatus('connected')
      }
    }

    eventSource.onmessage = (message) => {
      if (disposed) {
        return
      }
      try {
        const event = JSON.parse(message.data) as AgentEvent
        if (isResyncing) {
          bufferedEvents.push(event)
          return
        }
        applyEvent(event)
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
      useProjectStore.getState().setAgentConnectionStatus('reconnecting')
    }

    return () => {
      disposed = true
      eventSource.close()
      useProjectStore.getState().clearAgentState()
    }
  }, [nodeId, projectId])
}
