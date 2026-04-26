import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useProjectStore } from '../../stores/project-store'
import { useUIStore } from '../../stores/ui-store'
import styles from '../breadcrumb/BreadcrumbChatView.module.css'
import { useSessionFacadeV2 } from '../session_v2/facade/useSessionFacadeV2'
import { useThreadSessionStore } from '../session_v2/store/threadSessionStore'
import type { SessionItem } from '../session_v2/contracts'
import { getWorkflowContextV2, type WorkflowContextPacketV2 } from '../workflow_v2/api/client'
import { useWorkflowEventBridgeV2 } from '../workflow_v2/hooks/useWorkflowEventBridgeV2'
import { useWorkflowStateV2 } from '../workflow_v2/hooks/useWorkflowStateV2'
import type { WorkflowThreadRoleV2 } from '../workflow_v2/types'
import type { BreadcrumbDetailPaneProps } from './BreadcrumbChatViewV2'
import type { BreadcrumbThreadPaneV2Props } from './components/BreadcrumbThreadPaneV2'
import {
  buildChatV2Url,
  parseThreadTab,
  resolveV2RouteTarget,
  type ThreadTab,
} from './surfaceRouting'
import {
  buildWorkflowProjectionV2,
  resolveWorkflowSubmitTurnPolicyV2,
  type WorkflowLaneActionV2,
} from './workflowThreadLaneV2'

export type BreadcrumbConversationControllerV2 = {
  threadPaneProps: BreadcrumbThreadPaneV2Props
  detailPaneProps: BreadcrumbDetailPaneProps
}

type WorkflowThreadKeyV2 = 'askPlanning' | 'execution' | 'audit' | 'packageReview'

function workflowRoleForThreadTab(threadTab: ThreadTab): WorkflowThreadRoleV2 {
  if (threadTab === 'ask') {
    return 'ask_planning'
  }
  if (threadTab === 'package') {
    return 'package_review'
  }
  return threadTab
}

function buildWorkflowContextItem(
  packet: WorkflowContextPacketV2,
  role: WorkflowThreadRoleV2,
): SessionItem {
  const now = Date.now()
  return {
    id: `canonical-workflow-context-${role}-${packet.contextPacketHash}`,
    threadId: `workflow-context:${packet.projectId}:${packet.nodeId}:${role}`,
    turnId: `canonical-workflow-context-${role}-turn`,
    kind: 'systemMessage',
    normalizedKind: null,
    status: 'completed',
    createdAtMs: now,
    updatedAtMs: now,
    payload: {
      type: 'systemMessage',
      text: '',
      metadata: {
        workflowContext: true,
        workflowContextSource: 'node',
        role,
        packetKind: packet.kind,
        contextPacketHash: packet.contextPacketHash,
        contextPayload: packet.contextPayload,
        sourceVersions: packet.sourceVersions,
      },
    },
  }
}

function renderActionLabel(action: string | null, idleLabel: string, busyLabel: string): string {
  return action ? busyLabel : idleLabel
}

function terminalTurnStatusForRun(
  turns: Array<{ id: string; status?: string | null }>,
  run: Record<string, unknown> | null,
): string | null {
  const turnId = typeof run?.turnId === 'string' ? run.turnId : ''
  if (!turnId) {
    return null
  }
  const turn = turns.find((entry) => entry.id === turnId)
  const status = typeof turn?.status === 'string' ? turn.status : ''
  return status === 'completed' || status === 'failed' || status === 'interrupted' ? status : null
}

function resolveThreadFromMutationResult(
  result: { threadId?: string | null; workflowState?: { threads?: Record<string, string | null> } } | null | undefined,
  options: {
    workflowThreadKey: WorkflowThreadKeyV2
    laneFallbackThreadId: string | null
  },
): string | null {
  const direct = typeof result?.threadId === 'string' && result.threadId.trim().length > 0
    ? result.threadId
    : null
  if (direct) {
    return direct
  }
  const fromWorkflow = result?.workflowState?.threads?.[options.workflowThreadKey]
  if (typeof fromWorkflow === 'string' && fromWorkflow.trim().length > 0) {
    return fromWorkflow
  }
  return options.laneFallbackThreadId
}

function emitSessionCorrelation(payload: Record<string, unknown>): void {
  if (typeof window === 'undefined') {
    return
  }
  console.info('[session-v2-path] correlation', payload)
  window.dispatchEvent(new CustomEvent('session-v2-correlation', { detail: payload }))
}

export function useBreadcrumbConversationControllerV2(): BreadcrumbConversationControllerV2 {
  const navigate = useNavigate()
  const { projectId, nodeId } = useParams<{ projectId: string; nodeId: string }>()
  const [searchParams] = useSearchParams()
  const [showWorkflowContextItems, setShowWorkflowContextItems] = useState(false)
  const [workflowContextItem, setWorkflowContextItem] = useState<SessionItem | null>(null)
  const [sessionCorrelationHistory, setSessionCorrelationHistory] = useState<Record<string, unknown>[]>([])
  const detailStateKey = projectId && nodeId ? `${projectId}::${nodeId}` : ''
  const lastRouteSelectionSyncRef = useRef<string | null>(null)
  const lastThreadSnapshotTraceKeyRef = useRef<string | null>(null)
  const latestLaneThreadIdForResyncRef = useRef<string | null>(null)
  const isSelectingForResyncRef = useRef(false)
  const prevBreadcrumbThreadTabForResyncRef = useRef<ThreadTab | null>(null)
  const pendingLaneResyncAfterTabChangeRef = useRef(false)
  const lastTerminalWorkflowRefreshKeyRef = useRef<string | null>(null)
  const sessionFacade = useSessionFacadeV2({
    bootstrapPolicy: {
      autoBootstrapOnMount: true,
      autoSelectInitialThread: false,
      autoCreateThreadWhenEmpty: false,
    },
    pendingRequestScope: 'activeThread',
  })
  const { state: sessionState, commands: sessionCommands } = sessionFacade

  const {
    activeProjectId,
    snapshot,
    selectedNodeId,
    isLoadingSnapshot,
    error: projectError,
    loadProject,
    selectNode,
  } = useProjectStore(
    useShallow((state) => ({
      activeProjectId: state.activeProjectId,
      snapshot: state.snapshot,
      selectedNodeId: state.selectedNodeId,
      isLoadingSnapshot: state.isLoadingSnapshot,
      error: state.error,
      loadProject: state.loadProject,
      selectNode: state.selectNode,
    })),
  )

  const nodeDetailState = useDetailStateStore((state) =>
    detailStateKey ? state.entries[detailStateKey] : undefined,
  )
  const loadDetailState = useDetailStateStore((state) => state.loadDetailState)
  const setActiveSurface = useUIStore((state) => state.setActiveSurface)

  const {
    workflowState,
    isLoading: isWorkflowLoading,
    error: workflowError,
    activeMutation,
    mutationResult,
    loadWorkflowState,
    ensureThread,
    startExecution,
    completeExecution,
    startAudit,
    improveExecution,
    acceptAudit,
    startPackageReview,
  } = useWorkflowStateV2(projectId, nodeId)
  const sessionProjectionState = useThreadSessionStore(
    useShallow((state) => ({
      turnsByThread: state.turnsByThread,
      lastEventSeqByThread: state.lastEventSeqByThread,
      streamConnectedByThread: state.streamState.connectedByThread,
    })),
  )

  const isReviewNode = useMemo(() => {
    if (!projectId || !nodeId || !snapshot || snapshot.project.id !== projectId) {
      return false
    }
    const node = snapshot.tree_state.node_registry.find((candidate) => candidate.node_id === nodeId)
    return node?.node_kind === 'review'
  }, [nodeId, projectId, snapshot])

  const requestedThreadTab = parseThreadTab(searchParams.get('thread'))
  const isSessionDebugMode = searchParams.get('debugSession') === '1'
  const routeTarget = resolveV2RouteTarget({
    requestedThreadTab,
    isReviewNode,
  })
  const threadTab: ThreadTab = routeTarget.threadTab
  const shouldCanonicalizeV2 =
    routeTarget.surface !== 'v2' || requestedThreadTab !== routeTarget.threadTab

  useWorkflowEventBridgeV2(projectId, nodeId, Boolean(projectId && nodeId && !shouldCanonicalizeV2))

  useEffect(() => {
    if (!isSessionDebugMode || typeof window === 'undefined') {
      return
    }
    const appendTrace = (source: 'correlation' | 'gap_metric', detail: unknown) => {
      const entry =
        detail && typeof detail === 'object'
          ? ({
              source,
              at: new Date().toISOString(),
              ...(detail as Record<string, unknown>),
            })
          : ({
              source,
              at: new Date().toISOString(),
              detail,
            })
      setSessionCorrelationHistory((previous) => {
        const next = [...previous, entry]
        return next.length > 40 ? next.slice(next.length - 40) : next
      })
    }
    const onCorrelation = (event: Event) => {
      const custom = event as CustomEvent<Record<string, unknown> | undefined>
      appendTrace('correlation', custom.detail)
    }
    const onGapMetric = (event: Event) => {
      const custom = event as CustomEvent<Record<string, unknown> | undefined>
      appendTrace('gap_metric', custom.detail)
    }
    window.addEventListener('session-v2-correlation', onCorrelation as EventListener)
    window.addEventListener('session-v2-gap-metric', onGapMetric as EventListener)
    return () => {
      window.removeEventListener('session-v2-correlation', onCorrelation as EventListener)
      window.removeEventListener('session-v2-gap-metric', onGapMetric as EventListener)
    }
  }, [isSessionDebugMode])

  useEffect(() => {
    if (!projectId || !nodeId) {
      return
    }
    if (!snapshot || snapshot.project.id !== projectId) {
      return
    }
    if (shouldCanonicalizeV2) {
      void navigate(buildChatV2Url(projectId, nodeId, threadTab), { replace: true })
    }
  }, [navigate, nodeId, projectId, shouldCanonicalizeV2, snapshot, threadTab])

  useEffect(() => {
    if (!projectId) {
      return
    }
    if (snapshot?.project.id === projectId) {
      return
    }
    if (isLoadingSnapshot && activeProjectId === projectId) {
      return
    }
    if (projectError && activeProjectId === projectId) {
      return
    }
    void loadProject(projectId).catch(() => undefined)
  }, [activeProjectId, isLoadingSnapshot, loadProject, projectError, projectId, snapshot?.project.id])

  const detailNode = useMemo(() => {
    if (!projectId || !nodeId || !snapshot || snapshot.project.id !== projectId) {
      return null
    }
    return snapshot.tree_state.node_registry.find((node) => node.node_id === nodeId) ?? null
  }, [nodeId, projectId, snapshot])

  useEffect(() => {
    if (!projectId || !nodeId || !detailNode || !snapshot || snapshot.project.id !== projectId) {
      return
    }
    const routeKey = `${projectId}::${nodeId}`
    if (selectedNodeId === nodeId) {
      lastRouteSelectionSyncRef.current = routeKey
      return
    }
    if (lastRouteSelectionSyncRef.current === routeKey) {
      return
    }
    lastRouteSelectionSyncRef.current = routeKey
    void selectNode(nodeId, false).catch(() => undefined)
  }, [detailNode, nodeId, projectId, selectNode, selectedNodeId, snapshot])

  useEffect(() => {
    if (!projectId || !nodeId || !detailNode || !snapshot || snapshot.project.id !== projectId) {
      return
    }
    void loadDetailState(projectId, nodeId).catch(() => undefined)
  }, [detailNode, loadDetailState, nodeId, projectId, snapshot])

  useEffect(() => {
    if (
      !projectId ||
      !nodeId ||
      !detailNode ||
      !snapshot ||
      snapshot.project.id !== projectId ||
      shouldCanonicalizeV2
    ) {
      return
    }
    void loadWorkflowState(projectId, nodeId).catch(() => undefined)
  }, [detailNode, loadWorkflowState, nodeId, projectId, shouldCanonicalizeV2, snapshot])

  const workflowProjection = useMemo(
    () =>
      buildWorkflowProjectionV2({
        workflowState,
        activeLane: threadTab,
        selectedModel: sessionState.selectedModel,
        selectedModelProvider: sessionState.activeThread?.modelProvider ?? null,
        projectPath: snapshot?.project.project_path ?? sessionState.activeThread?.cwd ?? null,
        isReviewNode,
      }),
    [
      isReviewNode,
      sessionState.activeThread?.cwd,
      sessionState.activeThread?.modelProvider,
      sessionState.selectedModel,
      snapshot?.project.project_path,
      threadTab,
      workflowState,
    ],
  )
  const workflowLane = workflowProjection.lanes[threadTab]
  const activeThreadId = workflowLane.threadId
  latestLaneThreadIdForResyncRef.current = activeThreadId
  isSelectingForResyncRef.current = sessionState.isSelectingThread
  const workflowDebugStateRecord =
    workflowState && typeof workflowState === 'object'
      ? (workflowState as unknown as Record<string, unknown>)
      : {}
  const activeExecutionRunId =
    typeof workflowDebugStateRecord.activeExecutionRunId === 'string'
      ? workflowDebugStateRecord.activeExecutionRunId
      : null
  const activeAuditRunId =
    typeof workflowDebugStateRecord.activeAuditRunId === 'string'
      ? workflowDebugStateRecord.activeAuditRunId
      : null
  const activeExecutionRun =
    workflowDebugStateRecord.activeExecutionRun && typeof workflowDebugStateRecord.activeExecutionRun === 'object'
      ? (workflowDebugStateRecord.activeExecutionRun as Record<string, unknown>)
      : null
  const activeAuditRun =
    workflowDebugStateRecord.activeAuditRun && typeof workflowDebugStateRecord.activeAuditRun === 'object'
      ? (workflowDebugStateRecord.activeAuditRun as Record<string, unknown>)
      : null
  const shouldRecoverProviderOnResync = Boolean(
    (threadTab === 'execution' &&
      activeExecutionRun &&
      activeExecutionRun.threadId === activeThreadId &&
      activeExecutionRun.status === 'running') ||
      (threadTab === 'audit' &&
        activeAuditRun &&
        activeAuditRun.threadId === activeThreadId &&
        activeAuditRun.status === 'running'),
  )
  const laneTurns = activeThreadId ? sessionProjectionState.turnsByThread[activeThreadId] ?? [] : []
  const laneLastEventSeq = activeThreadId
    ? (sessionProjectionState.lastEventSeqByThread[activeThreadId] ?? null)
    : null
  const laneStreamConnected = activeThreadId
    ? Boolean(sessionProjectionState.streamConnectedByThread[activeThreadId])
    : false
  const activeRunForLane =
    threadTab === 'execution' ? activeExecutionRun : threadTab === 'audit' ? activeAuditRun : null
  const terminalRunStatusForLane = terminalTurnStatusForRun(laneTurns, activeRunForLane)

  useEffect(() => {
    if (!projectId || !nodeId || !activeThreadId || !activeRunForLane || !terminalRunStatusForLane) {
      return
    }
    const turnId = typeof activeRunForLane.turnId === 'string' ? activeRunForLane.turnId : ''
    if (!turnId) {
      return
    }
    const refreshKey = `${projectId}:${nodeId}:${threadTab}:${activeThreadId}:${turnId}:${terminalRunStatusForLane}`
    if (lastTerminalWorkflowRefreshKeyRef.current === refreshKey) {
      return
    }
    lastTerminalWorkflowRefreshKeyRef.current = refreshKey
    void loadWorkflowState(projectId, nodeId).catch(() => undefined)
  }, [
    activeRunForLane,
    activeThreadId,
    loadWorkflowState,
    nodeId,
    projectId,
    terminalRunStatusForLane,
    threadTab,
  ])

  useEffect(() => {
    if (!projectId || !nodeId) {
      setWorkflowContextItem(null)
      return
    }
    const role = workflowRoleForThreadTab(threadTab)
    let cancelled = false
    void getWorkflowContextV2(projectId, nodeId, role)
      .then((packet) => {
        if (cancelled) {
          return
        }
        setWorkflowContextItem(buildWorkflowContextItem(packet, role))
      })
      .catch(() => {
        // Keep the last canonical context while workflow/session hydration catches up.
      })
    return () => {
      cancelled = true
    }
  }, [
    nodeId,
    projectId,
    threadTab,
    workflowState?.context.frameVersion,
    workflowState?.context.specVersion,
    workflowState?.context.splitManifestVersion,
    workflowState?.version,
  ])

  const sessionDebugPayload = useMemo(
    () => ({
      projectId: projectId ?? null,
      nodeId: nodeId ?? null,
      lane: threadTab,
      phase: workflowState?.phase ?? null,
      workflowLaneThreadId: activeThreadId,
      sessionActiveThreadId: sessionState.activeThreadId,
      streamConnectedByThread: laneStreamConnected,
      turnsLength: laneTurns.length,
      lastEventSeqByThread: laneLastEventSeq,
      gapDetected: sessionState.gapDetected,
      reconnectCount: sessionState.reconnectCount,
      activeMutation,
      activeExecutionRunId,
      activeAuditRunId,
      activeExecutionRun: activeExecutionRun
        ? {
            runId: activeExecutionRun.runId ?? null,
            threadId: activeExecutionRun.threadId ?? null,
            turnId: activeExecutionRun.turnId ?? null,
            status: activeExecutionRun.status ?? null,
          }
        : null,
      activeAuditRun: activeAuditRun
        ? {
            runId: activeAuditRun.runId ?? null,
            threadId: activeAuditRun.threadId ?? null,
            turnId: activeAuditRun.turnId ?? null,
            status: activeAuditRun.status ?? null,
          }
        : null,
      mutationResult: mutationResult
        ? {
            threadId: mutationResult.threadId,
            turnId: mutationResult.turnId,
            executionRunId: mutationResult.executionRunId,
            auditRunId: mutationResult.auditRunId,
            reviewCycleId: mutationResult.reviewCycleId,
          }
        : null,
      traceEvents: isSessionDebugMode ? sessionCorrelationHistory : [],
    }),
    [
      activeAuditRun,
      activeAuditRunId,
      activeExecutionRun,
      activeExecutionRunId,
      activeMutation,
      activeThreadId,
      laneLastEventSeq,
      laneStreamConnected,
      laneTurns.length,
      mutationResult,
      nodeId,
      projectId,
      sessionState.activeThreadId,
      sessionState.gapDetected,
      sessionState.reconnectCount,
      sessionCorrelationHistory,
      threadTab,
      workflowState?.phase,
      isSessionDebugMode,
    ],
  )
  const autoEnsureRole =
    threadTab === 'ask'
      ? workflowProjection.lanes.ask.threadId
        ? null
        : ('ask_planning' as const)
      : !isReviewNode && workflowProjection.isLoaded && threadTab === 'execution'
        ? workflowProjection.lanes.execution.threadId
          ? null
          : ('execution' as const)
        : null
  const workflowModelPolicy = useMemo(
    () => ({
      model: sessionState.selectedModel,
      modelProvider: sessionState.activeThread?.modelProvider ?? null,
    }),
    [sessionState.activeThread?.modelProvider, sessionState.selectedModel],
  )

  useEffect(() => {
    if (
      !projectId ||
      !nodeId ||
      !detailNode ||
      !snapshot ||
      snapshot.project.id !== projectId ||
      shouldCanonicalizeV2 ||
      !workflowProjection.isLoaded
    ) {
      return
    }
    const laneThreadId = workflowLane.threadId
    const shouldHoldCurrentSelection = isWorkflowLoading || activeMutation !== null
    if (shouldHoldCurrentSelection) {
      emitSessionCorrelation({
        type: 'lane_sync_hold',
        projectId: projectId ?? null,
        nodeId: nodeId ?? null,
        lane: threadTab,
        workflowLaneThreadId: laneThreadId ?? null,
        sessionActiveThreadId: sessionState.activeThreadId,
      })
      return
    }
    if (laneThreadId) {
      if (sessionState.activeThreadId === laneThreadId) {
        return
      }
      emitSessionCorrelation({
        type: 'lane_sync_select',
        projectId: projectId ?? null,
        nodeId: nodeId ?? null,
        lane: threadTab,
        workflowLaneThreadId: laneThreadId,
        sessionActiveThreadId: sessionState.activeThreadId,
      })
      void sessionCommands.selectThread(laneThreadId).catch(() => undefined)
      return
    }
    if (sessionState.activeThreadId !== null) {
      emitSessionCorrelation({
        type: 'lane_sync_clear',
        projectId: projectId ?? null,
        nodeId: nodeId ?? null,
        lane: threadTab,
        workflowLaneThreadId: null,
        sessionActiveThreadId: sessionState.activeThreadId,
      })
      void sessionCommands.selectThread(null).catch(() => undefined)
    }
  }, [
    activeMutation,
    detailNode,
    isWorkflowLoading,
    nodeId,
    projectId,
    sessionState.activeThreadId,
    sessionCommands.selectThread,
    shouldCanonicalizeV2,
    snapshot,
    threadTab,
    workflowLane.threadId,
    workflowProjection.isLoaded,
  ])

  // After switching thread tabs, session selection can settle after this lane effect; mark pending so
  // we resync when active thread matches the lane (or after a short fallback timeout / tab focus).
  useEffect(() => {
    const previous = prevBreadcrumbThreadTabForResyncRef.current
    prevBreadcrumbThreadTabForResyncRef.current = threadTab
    if (previous === null) {
      return
    }
    if (previous === threadTab) {
      return
    }
    pendingLaneResyncAfterTabChangeRef.current = true
  }, [threadTab])

  useEffect(() => {
    if (!pendingLaneResyncAfterTabChangeRef.current) {
      return
    }
    if (!workflowProjection.isLoaded || sessionState.connection.phase !== 'initialized') {
      return
    }
    if (isSelectingForResyncRef.current) {
      return
    }
    const laneTid = latestLaneThreadIdForResyncRef.current
    if (!laneTid) {
      return
    }
    if (useThreadSessionStore.getState().activeThreadId !== laneTid) {
      return
    }
    pendingLaneResyncAfterTabChangeRef.current = false
    void sessionCommands.resyncThreadTranscript(laneTid, { recoverFromProvider: shouldRecoverProviderOnResync }).catch(() => undefined)
  }, [
    shouldRecoverProviderOnResync,
    sessionState.isSelectingThread,
    sessionState.activeThreadId,
    workflowLane.threadId,
    workflowProjection.isLoaded,
    sessionState.connection.phase,
    sessionCommands.resyncThreadTranscript,
  ])

  useEffect(() => {
    if (!pendingLaneResyncAfterTabChangeRef.current) {
      return
    }
    if (!workflowProjection.isLoaded || sessionState.connection.phase !== 'initialized') {
      return
    }
    const t = window.setTimeout(() => {
      if (!pendingLaneResyncAfterTabChangeRef.current) {
        return
      }
      if (isSelectingForResyncRef.current) {
        return
      }
      const laneTid = latestLaneThreadIdForResyncRef.current
      if (!laneTid) {
        return
      }
      if (useThreadSessionStore.getState().activeThreadId !== laneTid) {
        return
      }
      pendingLaneResyncAfterTabChangeRef.current = false
      void sessionCommands.resyncThreadTranscript(laneTid, { recoverFromProvider: shouldRecoverProviderOnResync }).catch(() => undefined)
    }, 400)
    return () => {
      window.clearTimeout(t)
    }
  }, [
    threadTab,
    sessionCommands.resyncThreadTranscript,
    sessionState.connection.phase,
    shouldRecoverProviderOnResync,
    workflowProjection.isLoaded,
  ])

  useEffect(() => {
    if (typeof document === 'undefined') {
      return
    }
    const onVisible = () => {
      if (document.visibilityState !== 'visible') {
        return
      }
      if (!workflowProjection.isLoaded || sessionState.connection.phase !== 'initialized') {
        return
      }
      if (isSelectingForResyncRef.current) {
        return
      }
      const laneTid = latestLaneThreadIdForResyncRef.current
      if (!laneTid) {
        return
      }
      if (useThreadSessionStore.getState().activeThreadId !== laneTid) {
        return
      }
      void sessionCommands.resyncThreadTranscript(laneTid, { recoverFromProvider: shouldRecoverProviderOnResync }).catch(() => undefined)
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [
    sessionCommands.resyncThreadTranscript,
    sessionState.connection.phase,
    shouldRecoverProviderOnResync,
    workflowProjection.isLoaded,
  ])

  useEffect(() => {
    if (!isSessionDebugMode || !projectId || !nodeId || !workflowProjection.isLoaded) {
      return
    }

    const workflowLaneThreadId = workflowLane.threadId ?? null
    const sessionActiveThreadId = sessionState.activeThreadId
    const traceThreadId = sessionActiveThreadId ?? workflowLaneThreadId
    const stateSnapshot = useThreadSessionStore.getState()
    const threadRecord = traceThreadId ? stateSnapshot.threadsById[traceThreadId] ?? null : null
    const turns = traceThreadId ? stateSnapshot.turnsByThread[traceThreadId] ?? [] : []
    const itemCount = turns.reduce((count, turn) => {
      return count + (Array.isArray(turn.items) ? turn.items.length : 0)
    }, 0)
    const traceKey = [
      projectId,
      nodeId,
      threadTab,
      workflowLaneThreadId ?? 'none',
      sessionActiveThreadId ?? 'none',
      String(turns.length),
      String(itemCount),
      String(traceThreadId ? stateSnapshot.lastEventSeqByThread[traceThreadId] ?? 'null' : 'null'),
      String(traceThreadId ? Boolean(stateSnapshot.streamState.connectedByThread[traceThreadId]) : false),
    ].join('|')

    if (lastThreadSnapshotTraceKeyRef.current === traceKey) {
      return
    }
    lastThreadSnapshotTraceKeyRef.current = traceKey

    emitSessionCorrelation({
      type: 'node_lane_thread_snapshot',
      projectId,
      nodeId,
      lane: threadTab,
      workflowLaneThreadId,
      sessionActiveThreadId,
      isLaneThreadSelected:
        workflowLaneThreadId !== null && workflowLaneThreadId === sessionActiveThreadId,
      traceThreadId,
      threadSnapshot: traceThreadId
        ? {
            threadId: traceThreadId,
            recordId: threadRecord?.id ?? null,
            status: stateSnapshot.threadStatus[traceThreadId]?.type ?? threadRecord?.status?.type ?? null,
            model: threadRecord?.model ?? null,
            modelProvider: threadRecord?.modelProvider ?? null,
            turnsCount: turns.length,
            turnIds: turns.slice(-5).map((turn) => turn.id),
            itemsCount: itemCount,
            lastEventSeq: stateSnapshot.lastEventSeqByThread[traceThreadId] ?? null,
            streamConnected: Boolean(stateSnapshot.streamState.connectedByThread[traceThreadId]),
          }
        : null,
    })
  }, [
    isSessionDebugMode,
    nodeId,
    projectId,
    sessionState.activeThreadId,
    threadTab,
    workflowLane.threadId,
    workflowProjection.isLoaded,
    sessionProjectionState.turnsByThread,
    sessionProjectionState.lastEventSeqByThread,
    sessionProjectionState.streamConnectedByThread,
  ])

  useEffect(() => {
    if (
      !projectId ||
      !nodeId ||
      !detailNode ||
      !snapshot ||
      snapshot.project.id !== projectId ||
      shouldCanonicalizeV2 ||
      activeMutation !== null ||
      sessionState.connection.phase !== 'initialized' ||
      !autoEnsureRole
    ) {
      return
    }
    void ensureThread(projectId, nodeId, autoEnsureRole, workflowModelPolicy).catch(() => undefined)
  }, [
    activeMutation,
    autoEnsureRole,
    detailNode,
    ensureThread,
    nodeId,
    projectId,
    sessionState.connection.phase,
    shouldCanonicalizeV2,
    snapshot,
    workflowModelPolicy,
  ])

  const detailCardState = useMemo(() => {
    if (!projectId || !nodeId) {
      return 'unavailable' as const
    }
    if (snapshot?.project.id === projectId && detailNode) {
      return 'ready' as const
    }
    if (isLoadingSnapshot && activeProjectId === projectId) {
      return 'loading' as const
    }
    if (!projectError && (!snapshot || snapshot.project.id !== projectId)) {
      return 'loading' as const
    }
    return 'unavailable' as const
  }, [activeProjectId, detailNode, isLoadingSnapshot, nodeId, projectError, projectId, snapshot])

  const detailMessage = useMemo(() => {
    if (!projectId || !nodeId) {
      return 'This breadcrumb route is missing its project or node id.'
    }
    if (detailCardState === 'loading') {
      return 'The node snapshot is loading for this breadcrumb route.'
    }
    if (projectError && activeProjectId === projectId) {
      return projectError
    }
    if (snapshot?.project.id === projectId && !detailNode) {
      return 'This node was not found in the current project snapshot.'
    }
    return 'Node details are unavailable for this breadcrumb route.'
  }, [activeProjectId, detailCardState, detailNode, nodeId, projectError, projectId, snapshot])

  const combinedError =
    workflowError ??
    sessionState.runtimeError ??
    sessionState.connection.error?.message ??
    null

  const isLaneThreadSelected = useMemo(() => {
    return Boolean(activeThreadId) && sessionState.activeThreadId === activeThreadId
  }, [activeThreadId, sessionState.activeThreadId])

  const composerDisabled = useMemo(() => {
    if (!workflowLane.policy.canSubmit) {
      return true
    }
    if (workflowLane.lane === 'ask') {
      return sessionState.connection.phase === 'error'
    }
    if (!activeThreadId) {
      return true
    }
    if (!isLaneThreadSelected) {
      return true
    }
    if (sessionState.isSelectingThread) {
      return true
    }
    if (!sessionState.isActiveThreadReady) {
      return true
    }
    return sessionState.connection.phase === 'error'
  }, [
    activeThreadId,
    isLaneThreadSelected,
    sessionState.connection.phase,
    sessionState.isActiveThreadReady,
    sessionState.isSelectingThread,
    workflowLane.lane,
    workflowLane.policy.canSubmit,
  ])

  const handleSubmit = useCallback(
    async (payload: Parameters<typeof sessionCommands.submit>[0]) => {
      if (!workflowLane.policy.canSubmit) {
        return
      }
      if (workflowLane.lane === 'ask' && projectId && nodeId) {
        let targetThreadId = workflowLane.threadId
        if (!targetThreadId) {
          const ensured = await ensureThread(projectId, nodeId, 'ask_planning', workflowModelPolicy)
          targetThreadId = resolveThreadFromMutationResult(ensured, {
            workflowThreadKey: 'askPlanning',
            laneFallbackThreadId: workflowLane.threadId,
          })
        }
        if (targetThreadId && sessionState.activeThreadId !== targetThreadId) {
          await sessionCommands.selectThread(targetThreadId)
        }
      }
      const turnPolicy = resolveWorkflowSubmitTurnPolicyV2({
        lane: workflowLane,
        requestedPolicy: payload.requestedPolicy,
      })
      await sessionCommands.submit(payload, turnPolicy)
      if (!projectId || !nodeId) {
        return
      }
      void loadWorkflowState(projectId, nodeId).catch(() => undefined)
    },
    [
      ensureThread,
      loadWorkflowState,
      nodeId,
      projectId,
      sessionCommands.selectThread,
      sessionCommands.submit,
      sessionState.activeThreadId,
      workflowLane,
      workflowModelPolicy,
    ],
  )

  const primeWorkflowTurnProjection = useCallback((options: {
    actionKind: WorkflowLaneActionV2['kind']
    targetLane: ThreadTab
    threadId: string | null
    turnId: string | null
  }) => {
    const threadId = typeof options.threadId === 'string' ? options.threadId.trim() : ''
    const turnId = typeof options.turnId === 'string' ? options.turnId.trim() : ''
    if (!threadId || !turnId) {
      return
    }

    const store = useThreadSessionStore.getState()
    const turns = store.turnsByThread[threadId] ?? []
    const alreadyPresent = turns.some((turn) => turn.id === turnId)
    if (!alreadyPresent) {
      const now = Date.now()
      store.setThreadTurns(threadId, [
        {
          id: turnId,
          threadId,
          status: 'inProgress',
          lastCodexStatus: 'inProgress',
          startedAtMs: now,
          completedAtMs: null,
          items: [],
          error: null,
        },
      ], { mode: 'merge' })
    }

    emitSessionCorrelation({
      type: alreadyPresent ? 'workflow_action_turn_present' : 'workflow_action_turn_primed',
      projectId: projectId ?? null,
      nodeId: nodeId ?? null,
      lane: options.targetLane,
      action: options.actionKind,
      threadId,
      turnId,
      turnsCount: (useThreadSessionStore.getState().turnsByThread[threadId] ?? []).length,
    })
  }, [nodeId, projectId])

  const handleWorkflowLaneAction = useCallback(
    async (action: WorkflowLaneActionV2) => {
      if (!projectId || !nodeId) {
        return
      }
      const navigateAndSelectThread = async (targetTab: ThreadTab, targetThreadId: string | null) => {
        emitSessionCorrelation({
          type: 'navigate_target_lane',
          projectId: projectId ?? null,
          nodeId: nodeId ?? null,
          lane: targetTab,
          threadId: targetThreadId,
        })
        void navigate(buildChatV2Url(projectId, nodeId, targetTab))
        if (!targetThreadId) {
          return
        }
        emitSessionCorrelation({
          type: 'select_thread_from_action',
          projectId: projectId ?? null,
          nodeId: nodeId ?? null,
          lane: targetTab,
          threadId: targetThreadId,
        })
        await sessionCommands.selectThread(targetThreadId)
      }
      if (action.kind === 'start_execution') {
        const result = await startExecution(projectId, nodeId, workflowModelPolicy)
        const threadId = resolveThreadFromMutationResult(result, {
          workflowThreadKey: 'execution',
          laneFallbackThreadId: workflowProjection.lanes.execution.threadId,
        })
        emitSessionCorrelation({
          type: 'workflow_action',
          action: action.kind,
          projectId,
          nodeId,
          role: 'execution',
          threadId: threadId ?? null,
          turnId: result.turnId ?? null,
          executionRunId: result.executionRunId ?? null,
          auditRunId: result.auditRunId ?? null,
        })
        primeWorkflowTurnProjection({
          actionKind: action.kind,
          targetLane: 'execution',
          threadId: threadId ?? null,
          turnId: result.turnId ?? null,
        })
        await navigateAndSelectThread('execution', threadId)
        return
      }
      if (action.kind === 'review_in_audit') {
        if (!action.candidateWorkspaceHash) {
          return
        }
        const result = await startAudit(projectId, nodeId, action.candidateWorkspaceHash, workflowModelPolicy)
        const threadId = resolveThreadFromMutationResult(result, {
          workflowThreadKey: 'audit',
          laneFallbackThreadId: workflowProjection.lanes.audit.threadId,
        })
        emitSessionCorrelation({
          type: 'workflow_action',
          action: action.kind,
          projectId,
          nodeId,
          role: 'audit',
          threadId: threadId ?? null,
          turnId: result.turnId ?? null,
          executionRunId: result.executionRunId ?? null,
          auditRunId: result.auditRunId ?? null,
        })
        primeWorkflowTurnProjection({
          actionKind: action.kind,
          targetLane: 'audit',
          threadId: threadId ?? null,
          turnId: result.turnId ?? null,
        })
        await navigateAndSelectThread('audit', threadId)
        return
      }
      if (action.kind === 'mark_done_from_execution') {
        if (!action.candidateWorkspaceHash) {
          return
        }
        await completeExecution(projectId, nodeId, action.candidateWorkspaceHash)
        setActiveSurface('graph')
        void navigate('/')
        return
      }
      if (action.kind === 'improve_in_execution') {
        if (!action.reviewCommitSha) {
          return
        }
        const result = await improveExecution(projectId, nodeId, action.reviewCommitSha, workflowModelPolicy)
        const threadId = resolveThreadFromMutationResult(result, {
          workflowThreadKey: 'execution',
          laneFallbackThreadId: workflowProjection.lanes.execution.threadId,
        })
        emitSessionCorrelation({
          type: 'workflow_action',
          action: action.kind,
          projectId,
          nodeId,
          role: 'execution',
          threadId: threadId ?? null,
          turnId: result.turnId ?? null,
          executionRunId: result.executionRunId ?? null,
          auditRunId: result.auditRunId ?? null,
        })
        primeWorkflowTurnProjection({
          actionKind: action.kind,
          targetLane: 'execution',
          threadId: threadId ?? null,
          turnId: result.turnId ?? null,
        })
        await navigateAndSelectThread('execution', threadId)
        return
      }
      if (action.kind === 'mark_done_from_audit') {
        if (!action.reviewCommitSha) {
          return
        }
        await acceptAudit(projectId, nodeId, action.reviewCommitSha)
        setActiveSurface('graph')
        void navigate('/')
        return
      }
      if (action.kind === 'start_package_review') {
        const result = await startPackageReview(projectId, nodeId, workflowModelPolicy)
        const threadId = resolveThreadFromMutationResult(result, {
          workflowThreadKey: 'packageReview',
          laneFallbackThreadId: workflowProjection.lanes.package.threadId,
        })
        emitSessionCorrelation({
          type: 'workflow_action',
          action: action.kind,
          projectId,
          nodeId,
          role: 'package_review',
          threadId: threadId ?? null,
          turnId: result.turnId ?? null,
          executionRunId: result.executionRunId ?? null,
          auditRunId: result.auditRunId ?? null,
        })
        primeWorkflowTurnProjection({
          actionKind: action.kind,
          targetLane: 'package',
          threadId: threadId ?? null,
          turnId: result.turnId ?? null,
        })
        await navigateAndSelectThread('package', threadId)
      }
    },
    [
      acceptAudit,
      completeExecution,
      improveExecution,
      navigate,
      nodeId,
      primeWorkflowTurnProjection,
      projectId,
      sessionCommands.selectThread,
      setActiveSurface,
      startAudit,
      startExecution,
      startPackageReview,
      workflowProjection.lanes.audit.threadId,
      workflowProjection.lanes.execution.threadId,
      workflowProjection.lanes.package.threadId,
      workflowModelPolicy,
    ],
  )

  const composerWorkflowActions = useMemo(() => {
    if (workflowLane.actions.length === 0) {
      return null
    }
    return (
      <>
        {workflowLane.actions.map((action) => (
          <button
            key={action.kind}
            type="button"
            className={`${styles.threadHeaderAction}${
              action.variant === 'primary' ? ` ${styles.threadHeaderActionPrimary}` : ''
            }`}
            disabled={activeMutation !== null}
            onClick={() => void handleWorkflowLaneAction(action)}
            data-testid={action.testId}
          >
            {renderActionLabel(activeMutation, action.idleLabel, action.busyLabel)}
          </button>
        ))}
      </>
    )
  }, [activeMutation, handleWorkflowLaneAction, workflowLane.actions])

  const handleThreadTabChange = useCallback(
    (nextThreadTab: ThreadTab) => {
      if (!projectId || !nodeId) {
        return
      }
      void navigate(buildChatV2Url(projectId, nodeId, nextThreadTab))
    },
    [navigate, nodeId, projectId],
  )

  const transcriptProps = useMemo(() => {
    if (!activeThreadId || !isLaneThreadSelected) {
      return {
        threadId: null,
        turns: [],
        itemsByTurn: {},
        workflowContextItem,
      }
    }
    return {
      threadId: sessionState.activeThreadId,
      turns: sessionState.activeTurns,
      itemsByTurn: sessionState.activeItemsByTurn,
      workflowContextItem,
    }
  }, [
    activeThreadId,
    isLaneThreadSelected,
    sessionState.activeItemsByTurn,
    sessionState.activeThreadId,
    sessionState.activeTurns,
    workflowContextItem,
  ])

  const composerProps = useMemo(
    () => ({
      isTurnRunning: Boolean(sessionState.activeRunningTurn),
      disabled: composerDisabled,
      onSubmit: handleSubmit,
      onInterrupt: sessionCommands.interrupt,
      currentCwd: sessionState.activeThread?.cwd ?? snapshot?.project.project_path ?? null,
      modelOptions: sessionState.modelOptions,
      selectedModel: sessionState.selectedModel,
      onModelChange: sessionCommands.setModel,
      isModelLoading: sessionState.isModelLoading,
    }),
    [
      composerDisabled,
      handleSubmit,
      sessionCommands.interrupt,
      sessionCommands.setModel,
      sessionState.activeRunningTurn,
      sessionState.activeThread?.cwd,
      sessionState.isModelLoading,
      sessionState.modelOptions,
      sessionState.selectedModel,
      snapshot?.project.project_path,
    ],
  )

  const pendingRequest = useMemo(() => {
    if (!activeThreadId || !isLaneThreadSelected) {
      return null
    }
    const request = sessionState.activeRequest
    if (!request) {
      return null
    }
    return request.threadId === activeThreadId ? request : null
  }, [activeThreadId, isLaneThreadSelected, sessionState.activeRequest])

  const pendingRequestProps = useMemo(
    () => ({
      request: pendingRequest,
      onResolve: sessionCommands.resolveRequest,
      onReject: sessionCommands.rejectRequest,
    }),
    [pendingRequest, sessionCommands.rejectRequest, sessionCommands.resolveRequest],
  )

  const workflowStripProps = useMemo(
    () => ({
      actions: composerWorkflowActions,
    }),
    [composerWorkflowActions],
  )

  const frameContextProps = useMemo(
    () => ({
      threadTab,
      onThreadTabChange: handleThreadTabChange,
      combinedError,
      projectId,
      nodeId,
      nodeRegistry: snapshot?.tree_state.node_registry ?? null,
      specConfirmed: nodeDetailState?.spec_confirmed === true,
    }),
    [
      combinedError,
      handleThreadTabChange,
      nodeDetailState?.spec_confirmed,
      nodeId,
      projectId,
      snapshot?.tree_state.node_registry,
      threadTab,
    ],
  )

  const threadPaneProps = useMemo(
    () => ({
      transcriptProps,
      frameContextProps,
      pendingRequestProps,
      workflowStripProps,
      composerProps,
      debugPanelProps: {
        enabled: isSessionDebugMode,
        payload: sessionDebugPayload,
        showWorkflowContextItems,
        onToggleShowWorkflowContextItems: () => {
          setShowWorkflowContextItems((previous) => !previous)
        },
      },
    }),
    [
      composerProps,
      frameContextProps,
      isSessionDebugMode,
      pendingRequestProps,
      sessionDebugPayload,
      showWorkflowContextItems,
      transcriptProps,
      workflowStripProps,
    ],
  )

  const detailPaneProps = useMemo(
    () => ({
      projectId: projectId ?? null,
      node: detailNode,
      state: detailCardState,
      message: detailMessage,
    }),
    [detailCardState, detailMessage, detailNode, projectId],
  )

  return {
    threadPaneProps,
    detailPaneProps,
  }
}
