import { useEffect } from 'react'

import { api } from './client'
import type { AgentEvent, AskEvent, ChatEvent, PlanningEvent } from './types'
import { useAskStore } from '../stores/ask-store'
import { useChatStore } from '../stores/chat-store'
import { useProjectStore } from '../stores/project-store'

export function useEffectOnce(effect: () => void | (() => void)) {
  useEffect(effect, [])
}

export function useChatSessionStream(projectId: string | null, nodeId: string | null) {
  useEffect(() => {
    const store = useChatStore.getState()
    if (!projectId || !nodeId) {
      store.clearSession()
      return () => {
        useChatStore.getState().setConnectionStatus('disconnected')
      }
    }

    const resolvedProjectId = projectId
    const resolvedNodeId = nodeId
    let disposed = false
    let streamOpen = false
    let hasConnectedOnce = false
    let isResyncing = true
    let lastEventSeq = 0
    let bufferedEvents: ChatEvent[] = []
    const eventSource = new EventSource(api.chatEventsUrl(resolvedProjectId, resolvedNodeId))

    function applyEvent(event: ChatEvent) {
      if (event.event_seq <= lastEventSeq) {
        return
      }
      lastEventSeq = event.event_seq
      useChatStore.getState().applyChatEvent(event)
      if (
        event.type === 'assistant_completed' ||
        event.type === 'assistant_error' ||
        event.type === 'plan_input_requested' ||
        event.type === 'plan_input_resolved' ||
        event.type === 'plan_runtime_status_changed'
      ) {
        void useProjectStore.getState().loadNodeDocuments(resolvedNodeId).catch(() => undefined)
      }
    }

    function flushBufferedEvents() {
      bufferedEvents
        .sort((left, right) => left.event_seq - right.event_seq)
        .forEach((event) => applyEvent(event))
      bufferedEvents = []
    }

    async function loadSession(connectionStatus: 'connecting' | 'reconnecting') {
      isResyncing = true
      bufferedEvents = []
      useChatStore.getState().setConnectionStatus(connectionStatus)
      useChatStore.getState().clearSession(true)
      try {
        await useChatStore.getState().loadSession(resolvedProjectId, resolvedNodeId)
        if (disposed) {
          return
        }
        lastEventSeq = useChatStore.getState().session?.event_seq ?? 0
        flushBufferedEvents()
        if (streamOpen) {
          useChatStore.getState().setConnectionStatus('connected')
        }
      } catch {
        if (!disposed) {
          useChatStore.getState().setConnectionStatus('disconnected')
        }
      } finally {
        isResyncing = false
      }
    }

    void loadSession('connecting')

    eventSource.onopen = () => {
      if (disposed) {
        return
      }
      streamOpen = true
      if (hasConnectedOnce) {
        void loadSession('reconnecting')
        return
      }
      hasConnectedOnce = true
      if (!isResyncing) {
        useChatStore.getState().setConnectionStatus('connected')
      }
    }

    eventSource.onmessage = (message) => {
      if (disposed) {
        return
      }
      try {
        const event = JSON.parse(message.data) as ChatEvent
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
      useChatStore.getState().setConnectionStatus('reconnecting')
    }

    return () => {
      disposed = true
      eventSource.close()
      useChatStore.getState().clearSession()
    }
  }, [nodeId, projectId])
}

export function useAskSessionStream(projectId: string | null, nodeId: string | null) {
  useEffect(() => {
    const store = useAskStore.getState()
    if (!projectId || !nodeId) {
      store.clearSession()
      return () => {
        useAskStore.getState().setConnectionStatus('disconnected')
      }
    }

    const resolvedProjectId = projectId
    const resolvedNodeId = nodeId
    let disposed = false
    let streamOpen = false
    let hasConnectedOnce = false
    let isResyncing = true
    let lastEventSeq = 0
    let bufferedEvents: AskEvent[] = []
    const eventSource = new EventSource(api.askEventsUrl(resolvedProjectId, resolvedNodeId))

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

    async function loadSession(connectionStatus: 'connecting' | 'reconnecting') {
      isResyncing = true
      bufferedEvents = []
      useAskStore.getState().setConnectionStatus(connectionStatus)
      useAskStore.getState().clearSession(true)
      try {
        await useAskStore.getState().loadSession(resolvedProjectId, resolvedNodeId)
        if (disposed) {
          return
        }
        lastEventSeq = useAskStore.getState().session?.event_seq ?? 0
        flushBufferedEvents()
        if (streamOpen) {
          useAskStore.getState().setConnectionStatus('connected')
        }
      } catch {
        if (!disposed) {
          useAskStore.getState().setConnectionStatus('disconnected')
        }
      } finally {
        isResyncing = false
      }
    }

    void loadSession('connecting')

    eventSource.onopen = () => {
      if (disposed) {
        return
      }
      streamOpen = true
      if (hasConnectedOnce) {
        void loadSession('reconnecting')
        return
      }
      hasConnectedOnce = true
      if (!isResyncing) {
        useAskStore.getState().setConnectionStatus('connected')
      }
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
      streamOpen = false
      isResyncing = true
      useAskStore.getState().setConnectionStatus('reconnecting')
    }

    return () => {
      disposed = true
      eventSource.close()
      useAskStore.getState().clearSession()
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
