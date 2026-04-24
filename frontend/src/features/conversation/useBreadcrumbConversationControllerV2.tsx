import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useProjectStore } from '../../stores/project-store'
import { useUIStore } from '../../stores/ui-store'
import styles from '../breadcrumb/BreadcrumbChatView.module.css'
import { toTurnExecutionPolicy } from '../session_v2/contracts'
import { useSessionFacadeV2 } from '../session_v2/facade/useSessionFacadeV2'
import type { BreadcrumbDetailPaneProps } from './BreadcrumbChatViewV2'
import type { BreadcrumbThreadPaneV2Props } from './components/BreadcrumbThreadPaneV2'
import {
  buildChatV2Url,
  parseThreadTab,
  resolveV2RouteTarget,
  type ThreadTab,
} from './surfaceRouting'
import { useWorkflowEventBridgeV3 } from './state/workflowEventBridgeV3'
import { useWorkflowStateStoreV3 } from './state/workflowStateStoreV3'
import {
  resolveWorkflowSubmitSessionConfig,
  resolveWorkflowThreadLane,
  type WorkflowLaneAction,
} from './workflowThreadLane'

export type BreadcrumbConversationControllerV2 = {
  threadPaneProps: BreadcrumbThreadPaneV2Props
  detailPaneProps: BreadcrumbDetailPaneProps
}

function renderActionLabel(action: string | null, idleLabel: string, busyLabel: string): string {
  return action ? busyLabel : idleLabel
}

export function useBreadcrumbConversationControllerV2(): BreadcrumbConversationControllerV2 {
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

  const workflowLane = useMemo(
    () =>
      resolveWorkflowThreadLane({
        workflowState,
        threadTab,
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
  const activeThreadId = workflowLane.threadId

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

  const isLaneThreadSelected = useMemo(() => {
    return Boolean(activeThreadId) && sessionState.activeThreadId === activeThreadId
  }, [activeThreadId, sessionState.activeThreadId])

  const composerDisabled = useMemo(() => {
    if (!workflowLane.policy.canSubmit) {
      return true
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
    workflowLane.policy.canSubmit,
  ])

  const handleSubmit = useCallback(
    async (payload: Parameters<typeof sessionCommands.submit>[0]) => {
      if (!workflowLane.policy.canSubmit) {
        return
      }
      const sessionConfig = resolveWorkflowSubmitSessionConfig({
        lane: workflowLane,
        accessMode: payload.accessMode,
        ...(payload.sessionConfig === undefined ? {} : { sessionConfig: payload.sessionConfig }),
      })
      await sessionCommands.submit(payload, toTurnExecutionPolicy(sessionConfig))
      if (!projectId || !nodeId) {
        return
      }
      void loadWorkflowState(projectId, nodeId).catch(() => undefined)
    },
    [loadWorkflowState, nodeId, projectId, sessionCommands.submit, workflowLane],
  )

  const handleWorkflowLaneAction = useCallback(
    async (action: WorkflowLaneAction) => {
      if (!projectId || !nodeId) {
        return
      }
      if (action.kind === 'reviewInAudit') {
        if (!action.candidateWorkspaceHash) {
          return
        }
        await reviewInAudit(projectId, nodeId, action.candidateWorkspaceHash)
        void navigate(buildChatV2Url(projectId, nodeId, 'audit'))
        return
      }
      if (action.kind === 'markDoneFromExecution') {
        if (!action.candidateWorkspaceHash) {
          return
        }
        await markDoneFromExecution(projectId, nodeId, action.candidateWorkspaceHash)
        setActiveSurface('graph')
        void navigate('/')
        return
      }
      if (action.kind === 'improveInExecution') {
        if (!action.reviewCommitSha) {
          return
        }
        await improveInExecution(projectId, nodeId, action.reviewCommitSha)
        void navigate(buildChatV2Url(projectId, nodeId, 'execution'))
        return
      }
      if (action.kind === 'markDoneFromAudit') {
        if (!action.reviewCommitSha) {
          return
        }
        await markDoneFromAudit(projectId, nodeId, action.reviewCommitSha)
        setActiveSurface('graph')
        void navigate('/')
      }
    },
    [
      improveInExecution,
      markDoneFromAudit,
      markDoneFromExecution,
      navigate,
      nodeId,
      projectId,
      reviewInAudit,
      setActiveSurface,
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

  const threadPaneProps = useMemo(
    () => ({
      transcriptProps,
      frameContextProps,
      pendingRequestProps,
      workflowStripProps,
      composerProps,
    }),
    [composerProps, frameContextProps, pendingRequestProps, transcriptProps, workflowStripProps],
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
