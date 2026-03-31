import { useCallback, useEffect, useMemo, useRef } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import type { ThreadRole } from '../../api/types'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useProjectStore } from '../../stores/project-store'
import { NodeDetailCard } from '../node/NodeDetailCard'
import { ComposerBar } from '../breadcrumb/ComposerBar'
import { FrameContextFeedBlock } from '../breadcrumb/FrameContextFeedBlock'
import {
  buildChatV2Url,
  buildLegacyChatUrl,
  isExecutionAuditV2SurfaceEnabled,
  parseThreadTab,
  resolveV2RouteTarget,
  type ThreadTab,
} from './surfaceRouting'
import styles from '../breadcrumb/BreadcrumbChatView.module.css'
import { ConversationFeed } from './components/ConversationFeed'
import { useThreadByIdStoreV2 } from './state/threadByIdStoreV2'
import { useWorkflowEventBridge } from './state/workflowEventBridge'
import { useWorkflowStateStoreV2 } from './state/workflowStateStoreV2'

function resolveThreadRole(threadTab: ThreadTab): ThreadRole | null {
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

  const {
    snapshot: conversationSnapshot,
    isLoading,
    isSending,
    processingStartedAt,
    lastCompletedAt,
    lastDurationMs,
    error,
    loadThread,
    sendTurn,
    resolveUserInput,
    disconnectThread,
  } = useThreadByIdStoreV2(
    useShallow((state) => ({
      snapshot: state.snapshot,
      isLoading: state.isLoading,
      isSending: state.isSending,
      processingStartedAt: state.processingStartedAt,
      lastCompletedAt: state.lastCompletedAt,
      lastDurationMs: state.lastDurationMs,
      error: state.error,
      loadThread: state.loadThread,
      sendTurn: state.sendTurn,
      resolveUserInput: state.resolveUserInput,
      disconnectThread: state.disconnectThread,
    })),
  )

  const {
    activeProjectId,
    bootstrap,
    snapshot,
    selectedNodeId,
    isLoadingSnapshot,
    error: projectError,
    loadProject,
    selectNode,
  } = useProjectStore(
    useShallow((state) => ({
      activeProjectId: state.activeProjectId,
      bootstrap: state.bootstrap,
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

  const {
    workflowState,
    isWorkflowLoading,
    workflowError,
    activeMutation,
    loadWorkflowState,
    finishTask,
    markDoneFromExecution,
    reviewInAudit,
    markDoneFromAudit,
    improveInExecution,
  } = useWorkflowStateStoreV2(
    useShallow((state) => ({
      workflowState: detailStateKey ? state.entries[detailStateKey] : undefined,
      isWorkflowLoading: detailStateKey ? state.loading[detailStateKey] === true : false,
      workflowError:
        detailStateKey && state.errors[detailStateKey] ? state.errors[detailStateKey] : null,
      activeMutation: detailStateKey ? state.activeMutations[detailStateKey] ?? null : null,
      loadWorkflowState: state.loadWorkflowState,
      finishTask: state.finishTask,
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
  const executionAuditV2Enabled = isExecutionAuditV2SurfaceEnabled(bootstrap)
  const routeTarget = resolveV2RouteTarget({
    requestedThreadTab,
    isReviewNode,
    executionAuditV2Enabled,
  })
  const threadTab: ThreadTab = routeTarget.threadTab
  const threadRole = resolveThreadRole(threadTab)
  const shouldRedirectToLegacy = routeTarget.surface === 'legacy'
  const shouldCanonicalizeV2 =
    routeTarget.surface === 'v2' && requestedThreadTab !== routeTarget.threadTab

  useWorkflowEventBridge(
    projectId,
    nodeId,
    Boolean(projectId && nodeId && !shouldRedirectToLegacy && !shouldCanonicalizeV2),
  )

  useEffect(() => {
    if (!projectId || !nodeId) {
      return
    }
    if (!snapshot || snapshot.project.id !== projectId) {
      return
    }
    if (shouldRedirectToLegacy) {
      void navigate(buildLegacyChatUrl(projectId, nodeId, threadTab), { replace: true })
      return
    }
    if (shouldCanonicalizeV2 && threadTab !== 'ask') {
      void navigate(buildChatV2Url(projectId, nodeId, threadTab), { replace: true })
    }
  }, [
    navigate,
    nodeId,
    projectId,
    shouldCanonicalizeV2,
    shouldRedirectToLegacy,
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
      shouldRedirectToLegacy ||
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
    shouldRedirectToLegacy,
    snapshot,
  ])

  const activeThreadId = useMemo(() => {
    if (!workflowState) {
      return null
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
      shouldRedirectToLegacy ||
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
    shouldRedirectToLegacy,
    snapshot,
    threadRole,
  ])

  useEffect(() => () => {
    disconnectThread()
  }, [disconnectThread])

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

  const isActiveTurn = Boolean(conversationSnapshot?.activeTurnId)
  const showAuditShell = threadTab === 'audit' && !workflowState?.reviewThreadId
  const composerDisabled =
    threadTab !== 'execution' ||
    workflowState?.canSendExecutionMessage !== true ||
    isActiveTurn ||
    isSending ||
    isLoading ||
    !conversationSnapshot

  const combinedError = error ?? workflowError ?? null
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

  const handleFinishTask = useCallback(async () => {
    if (!projectId || !nodeId) {
      return
    }
    await finishTask(projectId, nodeId)
  }, [finishTask, nodeId, projectId])

  const handleMarkDoneFromExecution = useCallback(async () => {
    if (!projectId || !nodeId || !currentExecutionDecision?.candidateWorkspaceHash) {
      return
    }
    await markDoneFromExecution(projectId, nodeId, currentExecutionDecision.candidateWorkspaceHash)
  }, [currentExecutionDecision?.candidateWorkspaceHash, markDoneFromExecution, nodeId, projectId])

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
  }, [currentAuditDecision?.reviewCommitSha, markDoneFromAudit, nodeId, projectId])

  const handleImproveInExecution = useCallback(async () => {
    if (!projectId || !nodeId || !currentAuditDecision?.reviewCommitSha) {
      return
    }
    await improveInExecution(projectId, nodeId, currentAuditDecision.reviewCommitSha)
    void navigate(buildChatV2Url(projectId, nodeId, 'execution'))
  }, [currentAuditDecision?.reviewCommitSha, improveInExecution, navigate, nodeId, projectId])

  const headerActions = useMemo(() => {
    if (!workflowState) {
      return null
    }

    if (threadTab === 'execution') {
      return (
        <>
          {workflowState.workflowPhase === 'idle' ? (
            <button
              type="button"
              className={`${styles.threadHeaderAction} ${styles.threadHeaderActionPrimary}`}
              disabled={activeMutation !== null || isWorkflowLoading}
              onClick={() => void handleFinishTask()}
              data-testid="workflow-finish-task"
            >
              {renderActionLabel(activeMutation, 'Finish Task', 'Starting...')}
            </button>
          ) : null}
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
    handleFinishTask,
    handleImproveInExecution,
    handleMarkDoneFromAudit,
    handleMarkDoneFromExecution,
    handleReviewInAudit,
    isWorkflowLoading,
    threadTab,
    workflowState,
  ])

  return (
    <div className={styles.root}>
      <div className={styles.threadPane} data-testid="breadcrumb-thread-pane">
        <div className={styles.threadSurface}>
          <div
            className={`${styles.threadTabBar} ${styles.threadTabBarSplit}`}
            data-testid="breadcrumb-v2-thread-header"
          >
            <nav className={styles.threadTabNav} role="tablist" aria-label="Thread mode">
              <button
                type="button"
                role="tab"
                className={`${styles.threadTab} ${threadTab === 'ask' ? styles.threadTabActive : ''}`}
                data-testid="breadcrumb-thread-tab-ask"
                aria-selected={threadTab === 'ask'}
                onClick={() => {
                  if (projectId && nodeId) {
                    void navigate(buildLegacyChatUrl(projectId, nodeId, 'ask'))
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

            <div className={styles.threadHeaderActions}>{headerActions}</div>
          </div>

          <div className={styles.threadTabBody}>
            {combinedError ? <div className={styles.errorBanner}>{combinedError}</div> : null}

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
              <ConversationFeed
                snapshot={conversationSnapshot}
                isLoading={isLoading || isWorkflowLoading}
                onResolveUserInput={resolveUserInput}
                processingStartedAt={processingStartedAt}
                lastCompletedAt={lastCompletedAt}
                lastDurationMs={lastDurationMs}
                prefix={
                  threadTab === 'audit' && snapshot && projectId && nodeId ? (
                    <FrameContextFeedBlock
                      projectId={projectId}
                      nodeId={nodeId}
                      nodeRegistry={snapshot.tree_state.node_registry}
                      variant="audit"
                      specConfirmed={nodeDetailState?.spec_confirmed === true}
                    />
                  ) : undefined
                }
              />
            )}

            <ComposerBar
              onSend={(content) => {
                void handleSend(content)
              }}
              disabled={composerDisabled}
            />
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
