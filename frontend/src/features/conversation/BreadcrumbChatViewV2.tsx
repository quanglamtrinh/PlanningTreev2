import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import type { ThreadRole } from '../../api/types'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useProjectStore } from '../../stores/project-store'
import { useUIStore } from '../../stores/ui-store'
import { NodeDetailCard } from '../node/NodeDetailCard'
import { ComposerBar } from '../breadcrumb/ComposerBar'
import { FrameContextFeedBlock } from '../breadcrumb/FrameContextFeedBlock'
import {
  buildChatV2Url,
  parseThreadTab,
  resolveV2RouteTarget,
  type ThreadTab,
} from './surfaceRouting'
import styles from '../breadcrumb/BreadcrumbChatView.module.css'
import { MessagesV3 } from './components/v3/MessagesV3'
import { MessagesV3ErrorBoundary } from './components/v3/MessagesV3ErrorBoundary'
import {
  selectComposerState,
  selectFeedRenderState,
  selectHistoryUiState,
  selectThreadActions,
  selectTransportBannerState,
  selectWorkflowActionState,
  useThreadByIdStoreV3,
} from './state/threadByIdStoreV3'
import { useWorkflowEventBridgeV3 } from './state/workflowEventBridgeV3'
import { useWorkflowStateStoreV3 } from './state/workflowStateStoreV3'

function resolveThreadRole(threadTab: ThreadTab): ThreadRole | null {
  if (threadTab === 'ask') {
    return 'ask_planning'
  }
  if (threadTab === 'execution') {
    return 'execution'
  }
  if (threadTab === 'audit') {
    return 'audit'
  }
  return null
}

function renderActionLabel(action: string | null, idleLabel: string, busyLabel: string): string {
  return action ? busyLabel : idleLabel
}

export function BreadcrumbChatViewV2() {
  const navigate = useNavigate()
  const { projectId, nodeId } = useParams<{ projectId: string; nodeId: string }>()
  const [searchParams] = useSearchParams()
  const detailStateKey = projectId && nodeId ? `${projectId}::${nodeId}` : ''
  const lastRouteSelectionSyncRef = useRef<string | null>(null)

  const feedRenderStateV3 = useThreadByIdStoreV3(useShallow(selectFeedRenderState))
  const historyUiStateV3 = useThreadByIdStoreV3(useShallow(selectHistoryUiState))
  const composerStateV3 = useThreadByIdStoreV3(useShallow(selectComposerState))
  const transportBannerStateV3 = useThreadByIdStoreV3(useShallow(selectTransportBannerState))
  const workflowActionStateV3 = useThreadByIdStoreV3(useShallow(selectWorkflowActionState))
  const {
    loadThread: loadThreadV3,
    loadMoreHistory: loadMoreHistoryV3,
    sendTurn: sendTurnV3,
    resolveUserInput: resolveUserInputV3,
    runPlanAction: runPlanActionV3,
    recordRenderError: recordV3RenderError,
    disconnectThread: disconnectThreadV3,
  } = useThreadByIdStoreV3(useShallow(selectThreadActions))

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
    isWorkflowLoading,
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
      isWorkflowLoading: detailStateKey ? state.loading[detailStateKey] === true : false,
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
  const isLoading = feedRenderStateV3.isLoading
  const isSending = feedRenderStateV3.isSending
  const hasOlderHistory = historyUiStateV3.hasOlderHistory
  const isLoadingHistory = historyUiStateV3.isLoadingHistory
  const historyError = historyUiStateV3.historyError
  const lastCompletedAt = workflowActionStateV3.lastCompletedAt
  const lastDurationMs = workflowActionStateV3.lastDurationMs
  const error = transportBannerStateV3.error ?? feedRenderStateV3.error
  const loadThread = loadThreadV3
  const loadMoreHistory = loadMoreHistoryV3
  const sendTurn = sendTurnV3
  const resolveUserInput = resolveUserInputV3
  const disconnectThread = disconnectThreadV3
  const threadRole = resolveThreadRole(threadTab)
  const shouldCanonicalizeV2 = routeTarget.surface !== 'v2' || requestedThreadTab !== routeTarget.threadTab

  useWorkflowEventBridgeV3(
    projectId,
    nodeId,
    Boolean(projectId && nodeId && !shouldCanonicalizeV2),
  )

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
  }, [
    navigate,
    nodeId,
    projectId,
    shouldCanonicalizeV2,
    snapshot,
    threadTab,
  ])

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
  }, [
    detailNode,
    loadWorkflowState,
    nodeId,
    projectId,
    shouldCanonicalizeV2,
    snapshot,
  ])

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
    if (!activeThreadId || !threadRole) {
      disconnectThread()
      return
    }
    void loadThread(projectId, nodeId, activeThreadId, threadRole).catch(() => undefined)
  }, [
    activeThreadId,
    detailNode,
    disconnectThread,
    loadThread,
    nodeId,
    projectId,
    shouldCanonicalizeV2,
    snapshot,
    threadRole,
  ])

  useEffect(() => () => {
    disconnectThreadV3()
  }, [disconnectThreadV3])

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

  const showAuditShell = threadTab === 'audit' && !workflowState?.reviewThreadId
  const isActiveTurn = composerStateV3.isActiveTurn
  const composerDisabled = useMemo(() => {
    if (!composerStateV3.snapshot) {
      return true
    }
    if (threadTab === 'ask') {
      return isActiveTurn || composerStateV3.isSending || composerStateV3.isLoading
    }
    if (threadTab === 'execution') {
      return (
        workflowState?.canSendExecutionMessage !== true ||
        isActiveTurn ||
        composerStateV3.isSending ||
        composerStateV3.isLoading
      )
    }
    return true
  }, [composerStateV3.isLoading, composerStateV3.isSending, composerStateV3.snapshot, isActiveTurn, threadTab, workflowState])

  const combinedError = error ?? workflowError ?? historyError ?? null
  const currentExecutionDecision = workflowState?.currentExecutionDecision ?? null
  const currentAuditDecision = workflowState?.currentAuditDecision ?? null

  const handleSend = useCallback(
    async (content: string) => {
      if (!projectId || !nodeId) {
        return
      }
      await sendTurn(content)
      void loadWorkflowState(projectId, nodeId).catch(() => undefined)
    },
    [loadWorkflowState, nodeId, projectId, sendTurn],
  )

  const handleV3RenderError = useCallback(
    (error: Error) => {
      recordV3RenderError(error.message || 'Failed to render V3 conversation.')
    },
    [recordV3RenderError],
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

  return (
    <div className={styles.root}>
      <div className={styles.threadPane} data-testid="breadcrumb-thread-pane">
        <div className={styles.threadSurface}>
          <div className={styles.threadTabBar} data-testid="breadcrumb-v2-thread-header">
            <nav className={styles.threadTabNav} role="tablist" aria-label="Thread mode">
              <button
                type="button"
                role="tab"
                className={`${styles.threadTab} ${threadTab === 'ask' ? styles.threadTabActive : ''}`}
                data-testid="breadcrumb-thread-tab-ask"
                aria-selected={threadTab === 'ask'}
                onClick={() => {
                  if (projectId && nodeId) {
                    void navigate(buildChatV2Url(projectId, nodeId, 'ask'))
                  }
                }}
              >
                Ask
              </button>
              <button
                type="button"
                role="tab"
                className={`${styles.threadTab} ${threadTab === 'execution' ? styles.threadTabActive : ''}`}
                data-testid="breadcrumb-thread-tab-execution"
                aria-selected={threadTab === 'execution'}
                onClick={() => {
                  if (projectId && nodeId) {
                    void navigate(buildChatV2Url(projectId, nodeId, 'execution'))
                  }
                }}
              >
                Execution
              </button>
              <button
                type="button"
                role="tab"
                className={`${styles.threadTab} ${threadTab === 'audit' ? styles.threadTabActive : ''}`}
                data-testid="breadcrumb-thread-tab-audit"
                aria-selected={threadTab === 'audit'}
                onClick={() => {
                  if (projectId && nodeId) {
                    void navigate(buildChatV2Url(projectId, nodeId, 'audit'))
                  }
                }}
              >
                Audit
              </button>
            </nav>
          </div>

          <div className={styles.threadTabBody} data-testid="breadcrumb-thread-body">
            <div className={styles.threadBodyNoticeRow}>
              {combinedError ? (
                <div className={styles.errorBanner} role="alert">
                  {combinedError}
                </div>
              ) : null}
            </div>

            <div
              className={`${styles.threadBodyMain}${
                threadTab === 'execution' ? ` ${styles.threadExecutionWhiteCanvas}` : ''
              }`}
            >
              {showAuditShell ? (
                <div className={styles.auditShell} data-testid="audit-shell">
                  {snapshot && projectId && nodeId ? (
                    <FrameContextFeedBlock
                      projectId={projectId}
                      nodeId={nodeId}
                      nodeRegistry={snapshot.tree_state.node_registry}
                      variant="audit"
                      specConfirmed={nodeDetailState?.spec_confirmed === true}
                    />
                  ) : null}
                  <div className={styles.auditShellBody}>
                    <div className={styles.auditShellTitle}>Audit Review Not Started Yet</div>
                    <div className={styles.auditShellText}>
                      Start review from the execution tab once the current execution decision is ready.
                    </div>
                  </div>
                </div>
              ) : (
                <MessagesV3ErrorBoundary
                  key={`${threadTab}:${activeThreadId ?? 'none'}`}
                  onRenderError={handleV3RenderError}
                >
                  <MessagesV3
                    snapshot={feedRenderStateV3.snapshot}
                    isLoading={isLoading || isWorkflowLoading}
                    isSending={isSending}
                    hasOlderHistory={hasOlderHistory}
                    isLoadingHistory={isLoadingHistory}
                    onLoadMoreHistory={() => void loadMoreHistory()}
                    onResolveUserInput={resolveUserInput}
                    onPlanAction={runPlanActionV3}
                    lastCompletedAt={lastCompletedAt}
                    lastDurationMs={lastDurationMs}
                    threadChatFlatCanvas
                    prefix={
                      (threadTab === 'ask' || threadTab === 'audit') && snapshot && projectId && nodeId ? (
                        <FrameContextFeedBlock
                          projectId={projectId}
                          nodeId={nodeId}
                          nodeRegistry={snapshot.tree_state.node_registry}
                          variant={threadTab === 'audit' ? 'audit' : 'ask'}
                          specConfirmed={nodeDetailState?.spec_confirmed === true}
                        />
                      ) : undefined
                    }
                    suffix={composerWorkflowActions ?? undefined}
                  />
                </MessagesV3ErrorBoundary>
              )}
            </div>

            <div
              className={`${styles.threadBodyComposer}${
                threadTab === 'execution' ? ` ${styles.threadExecutionWhiteCanvas}` : ''
              }`}
              data-testid="breadcrumb-thread-composer"
            >
              <ComposerBar
                onSend={(content) => {
                  void handleSend(content)
                }}
                disabled={composerDisabled}
              />
            </div>
          </div>
        </div>
      </div>

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
