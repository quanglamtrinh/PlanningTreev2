import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useProjectStore } from '../../stores/project-store'
import { useUIStore } from '../../stores/ui-store'
import styles from '../breadcrumb/BreadcrumbChatView.module.css'
import { NodeDetailCard } from '../node/NodeDetailCard'
import { useSessionFacadeV2 } from '../session_v2/facade/useSessionFacadeV2'
import { BreadcrumbThreadPaneV2 } from './components/BreadcrumbThreadPaneV2'
import {
  buildChatV2Url,
  parseThreadTab,
  resolveV2RouteTarget,
  type ThreadTab,
} from './surfaceRouting'
import { useWorkflowEventBridgeV3 } from './state/workflowEventBridgeV3'
import { useWorkflowStateStoreV3 } from './state/workflowStateStoreV3'

function renderActionLabel(action: string | null, idleLabel: string, busyLabel: string): string {
  return action ? busyLabel : idleLabel
}

export function BreadcrumbChatViewV2() {
  const navigate = useNavigate()
  const { projectId, nodeId } = useParams<{ projectId: string; nodeId: string }>()
  const [searchParams] = useSearchParams()
  const detailStateKey = projectId && nodeId ? `${projectId}::${nodeId}` : ''
  const lastRouteSelectionSyncRef = useRef<string | null>(null)
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
    workflowError,
    activeMutation,
    loadWorkflowState,
    markDoneFromExecution,
    reviewInAudit,
    markDoneFromAudit,
    improveInExecution,
  } = useWorkflowStateStoreV3(
    useShallow((state) => ({
      workflowState: detailStateKey ? state.entries[detailStateKey] : undefined,
      workflowError:
        detailStateKey && state.errors[detailStateKey] ? state.errors[detailStateKey] : null,
      activeMutation: detailStateKey ? state.activeMutations[detailStateKey] ?? null : null,
      loadWorkflowState: state.loadWorkflowState,
      markDoneFromExecution: state.markDoneFromExecution,
      reviewInAudit: state.reviewInAudit,
      markDoneFromAudit: state.markDoneFromAudit,
      improveInExecution: state.improveInExecution,
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
  const routeTarget = resolveV2RouteTarget({
    requestedThreadTab,
    isReviewNode,
  })
  const threadTab: ThreadTab = routeTarget.threadTab
  const shouldCanonicalizeV2 =
    routeTarget.surface !== 'v2' || requestedThreadTab !== routeTarget.threadTab

  useWorkflowEventBridgeV3(projectId, nodeId, Boolean(projectId && nodeId && !shouldCanonicalizeV2))

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

  const activeThreadId = useMemo(() => {
    if (!workflowState) {
      return null
    }
    if (threadTab === 'ask') {
      return workflowState.askThreadId ?? null
    }
    if (threadTab === 'execution') {
      return workflowState.executionThreadId
    }
    if (threadTab === 'audit') {
      return workflowState.reviewThreadId
    }
    return null
  }, [threadTab, workflowState])

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
    void sessionCommands.selectThread(activeThreadId ?? null).catch(() => undefined)
  }, [
    activeThreadId,
    detailNode,
    nodeId,
    projectId,
    sessionCommands.selectThread,
    shouldCanonicalizeV2,
    snapshot,
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
  const currentExecutionDecision = workflowState?.currentExecutionDecision ?? null
  const currentAuditDecision = workflowState?.currentAuditDecision ?? null

  const isLaneThreadSelected = useMemo(() => {
    return Boolean(activeThreadId) && sessionState.activeThreadId === activeThreadId
  }, [activeThreadId, sessionState.activeThreadId])

  const composerDisabled = useMemo(() => {
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
  ])

  const handleSubmit = useCallback(
    async (payload: Parameters<typeof sessionCommands.submit>[0]) => {
      await sessionCommands.submit(payload)
      if (!projectId || !nodeId) {
        return
      }
      void loadWorkflowState(projectId, nodeId).catch(() => undefined)
    },
    [loadWorkflowState, nodeId, projectId, sessionCommands.submit],
  )

  const handleMarkDoneFromExecution = useCallback(async () => {
    if (!projectId || !nodeId || !currentExecutionDecision?.candidateWorkspaceHash) {
      return
    }
    await markDoneFromExecution(projectId, nodeId, currentExecutionDecision.candidateWorkspaceHash)
    setActiveSurface('graph')
    void navigate('/')
  }, [
    currentExecutionDecision?.candidateWorkspaceHash,
    markDoneFromExecution,
    navigate,
    nodeId,
    projectId,
    setActiveSurface,
  ])

  const handleReviewInAudit = useCallback(async () => {
    if (!projectId || !nodeId || !currentExecutionDecision?.candidateWorkspaceHash) {
      return
    }
    await reviewInAudit(projectId, nodeId, currentExecutionDecision.candidateWorkspaceHash)
    void navigate(buildChatV2Url(projectId, nodeId, 'audit'))
  }, [currentExecutionDecision?.candidateWorkspaceHash, navigate, nodeId, projectId, reviewInAudit])

  const handleMarkDoneFromAudit = useCallback(async () => {
    if (!projectId || !nodeId || !currentAuditDecision?.reviewCommitSha) {
      return
    }
    await markDoneFromAudit(projectId, nodeId, currentAuditDecision.reviewCommitSha)
    setActiveSurface('graph')
    void navigate('/')
  }, [
    currentAuditDecision?.reviewCommitSha,
    markDoneFromAudit,
    navigate,
    nodeId,
    projectId,
    setActiveSurface,
  ])

  const handleImproveInExecution = useCallback(async () => {
    if (!projectId || !nodeId || !currentAuditDecision?.reviewCommitSha) {
      return
    }
    await improveInExecution(projectId, nodeId, currentAuditDecision.reviewCommitSha)
    void navigate(buildChatV2Url(projectId, nodeId, 'execution'))
  }, [currentAuditDecision?.reviewCommitSha, improveInExecution, navigate, nodeId, projectId])

  const composerWorkflowActions = useMemo(() => {
    if (!workflowState) {
      return null
    }

    if (threadTab === 'execution') {
      if (!workflowState.canReviewInAudit && !workflowState.canMarkDoneFromExecution) {
        return null
      }
      return (
        <>
          {workflowState.canReviewInAudit ? (
            <button
              type="button"
              className={styles.threadHeaderAction}
              disabled={activeMutation !== null}
              onClick={() => void handleReviewInAudit()}
              data-testid="workflow-review-in-audit"
            >
              {renderActionLabel(activeMutation, 'Review in Audit', 'Starting Review...')}
            </button>
          ) : null}
          {workflowState.canMarkDoneFromExecution ? (
            <button
              type="button"
              className={`${styles.threadHeaderAction} ${styles.threadHeaderActionPrimary}`}
              disabled={activeMutation !== null}
              onClick={() => void handleMarkDoneFromExecution()}
              data-testid="workflow-mark-done-execution"
            >
              {renderActionLabel(activeMutation, 'Mark Done', 'Marking Done...')}
            </button>
          ) : null}
        </>
      )
    }

    if (threadTab === 'audit') {
      if (!workflowState.canImproveInExecution && !workflowState.canMarkDoneFromAudit) {
        return null
      }
      return (
        <>
          {workflowState.canImproveInExecution ? (
            <button
              type="button"
              className={styles.threadHeaderAction}
              disabled={activeMutation !== null}
              onClick={() => void handleImproveInExecution()}
              data-testid="workflow-improve-in-execution"
            >
              {renderActionLabel(activeMutation, 'Improve in Execution', 'Starting Improve...')}
            </button>
          ) : null}
          {workflowState.canMarkDoneFromAudit ? (
            <button
              type="button"
              className={`${styles.threadHeaderAction} ${styles.threadHeaderActionPrimary}`}
              disabled={activeMutation !== null}
              onClick={() => void handleMarkDoneFromAudit()}
              data-testid="workflow-mark-done-audit"
            >
              {renderActionLabel(activeMutation, 'Mark Done', 'Marking Done...')}
            </button>
          ) : null}
        </>
      )
    }

    return null
  }, [
    activeMutation,
    handleImproveInExecution,
    handleMarkDoneFromAudit,
    handleMarkDoneFromExecution,
    handleReviewInAudit,
    threadTab,
    workflowState,
  ])

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
      }
    }
    return {
      threadId: sessionState.activeThreadId,
      turns: sessionState.activeTurns,
      itemsByTurn: sessionState.activeItemsByTurn,
    }
  }, [
    activeThreadId,
    isLaneThreadSelected,
    sessionState.activeItemsByTurn,
    sessionState.activeThreadId,
    sessionState.activeTurns,
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

  return (
    <div className={styles.root}>
      <BreadcrumbThreadPaneV2
        transcriptProps={transcriptProps}
        frameContextProps={frameContextProps}
        pendingRequestProps={pendingRequestProps}
        workflowStripProps={workflowStripProps}
        composerProps={composerProps}
      />

      <aside className={styles.detailPane} data-testid="breadcrumb-detail-pane">
        <div className={styles.detailRail}>
          <NodeDetailCard
            projectId={projectId ?? null}
            node={detailNode}
            variant="breadcrumb"
            showClose={false}
            state={detailCardState}
            message={detailMessage}
          />
        </div>
      </aside>
    </div>
  )
}
