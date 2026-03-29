import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { useConversationThreadStoreV2 } from './state/threadStoreV2'
import { useWorkflowEventBridge } from './state/workflowEventBridge'

function isThreadComposerReadOnly(
  threadRole: ThreadRole,
  shapingFrozen: boolean,
  auditWritable: boolean,
): boolean {
  switch (threadRole) {
    case 'ask_planning':
      return shapingFrozen
    case 'execution':
      return true
    case 'audit':
      return !auditWritable
    default:
      return true
  }
}

function resolveThreadRole(isReviewNode: boolean, threadTab: ThreadTab): ThreadRole {
  if (isReviewNode) {
    return 'audit'
  }
  return threadTab === 'ask' ? 'ask_planning' : threadTab
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
    isResetting,
    error,
    loadThread,
    sendTurn,
    resolveUserInput,
    resetThread,
    disconnectThread,
  } = useConversationThreadStoreV2(
    useShallow((state) => ({
      snapshot: state.snapshot,
      isLoading: state.isLoading,
      isSending: state.isSending,
      isResetting: state.isResetting,
      error: state.error,
      loadThread: state.loadThread,
      sendTurn: state.sendTurn,
      resolveUserInput: state.resolveUserInput,
      resetThread: state.resetThread,
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
  const acceptLocalReviewAction = useDetailStateStore((state) => state.acceptLocalReview)

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
  const threadRole = resolveThreadRole(isReviewNode, threadTab)
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
    void loadThread(projectId, nodeId, threadRole)
  }, [
    detailNode,
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

  const [reviewSummaryDraft, setReviewSummaryDraft] = useState('')
  const [isAccepting, setIsAccepting] = useState(false)
  const [acceptReviewError, setAcceptReviewError] = useState<string | null>(null)
  const reviewInputRef = useRef<HTMLInputElement>(null)

  const canAcceptLocalReview = nodeDetailState?.can_accept_local_review === true
  const autoReviewStatus = nodeDetailState?.auto_review_status ?? null
  const showAcceptReview = threadTab === 'audit' && canAcceptLocalReview && !autoReviewStatus

  useEffect(() => {
    if (!showAcceptReview) {
      setAcceptReviewError(null)
    }
  }, [nodeId, projectId, showAcceptReview])

  const handleAcceptReview = useCallback(async () => {
    const summary = reviewSummaryDraft.trim()
    if (!summary || !projectId || !nodeId) {
      return
    }
    setIsAccepting(true)
    setAcceptReviewError(null)
    try {
      const activatedSiblingId = await acceptLocalReviewAction(projectId, nodeId, summary)
      setReviewSummaryDraft('')
      setAcceptReviewError(null)
      if (activatedSiblingId) {
        void navigate(buildLegacyChatUrl(projectId, activatedSiblingId, 'ask'))
      }
    } catch (caughtError) {
      setAcceptReviewError(caughtError instanceof Error ? caughtError.message : String(caughtError))
      reviewInputRef.current?.focus()
    } finally {
      setIsAccepting(false)
    }
  }, [acceptLocalReviewAction, navigate, nodeId, projectId, reviewSummaryDraft])

  const isActiveTurn = !!conversationSnapshot?.activeTurnId
  const shapingFrozen =
    nodeDetailState?.shaping_frozen ?? (detailNode?.workflow?.shaping_frozen === true)
  const auditWritable = nodeDetailState?.audit_writable === true
  const threadReadOnly = useMemo(
    () => isThreadComposerReadOnly(threadRole, shapingFrozen, auditWritable),
    [auditWritable, shapingFrozen, threadRole],
  )
  const composerDisabled =
    threadReadOnly || isActiveTurn || isSending || isLoading || !conversationSnapshot

  const showResetAction = !isReviewNode && threadTab === 'ask' && !threadReadOnly
  const disableResetAction = isActiveTurn || isLoading || isResetting

  const handleResetThread = useCallback(async () => {
    if (!window.confirm('Reset this thread?')) {
      return
    }
    await resetThread()
  }, [resetThread])

  return (
    <div className={styles.root}>
      <div
        className={`${styles.threadPane} ${isReviewNode ? styles.threadPaneSolo : ''}`}
        data-testid="breadcrumb-thread-pane"
      >
        <div className={styles.threadSurface}>
          {isReviewNode ? (
            <div className={styles.threadTabBar} data-testid="breadcrumb-review-audit-header">
              <span
                className={`${styles.threadTab} ${styles.threadTabActive}`}
                data-testid="breadcrumb-thread-tab-review-audit"
              >
                Review Audit
              </span>
            </div>
          ) : (
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

              {showResetAction ? (
                <div className={styles.threadHeaderActions}>
                  <button
                    type="button"
                    className={styles.threadHeaderAction}
                    disabled={disableResetAction}
                    onClick={() => void handleResetThread()}
                    data-testid="breadcrumb-v2-reset-thread"
                  >
                    {isResetting ? 'Resetting…' : 'Reset Thread'}
                  </button>
                </div>
              ) : null}
            </div>
          )}

          <div className={styles.threadTabBody}>
            <>
              {error ? <div className={styles.errorBanner}>{error}</div> : null}
              <ConversationFeed
                snapshot={conversationSnapshot}
                isLoading={isLoading}
                onResolveUserInput={resolveUserInput}
                prefix={
                  (threadTab === 'ask' || threadTab === 'audit') &&
                  !isReviewNode &&
                  snapshot &&
                  projectId &&
                  nodeId ? (
                    <FrameContextFeedBlock
                      projectId={projectId}
                      nodeId={nodeId}
                      nodeRegistry={snapshot.tree_state.node_registry}
                      variant={threadTab === 'audit' ? 'audit' : 'ask'}
                      specConfirmed={nodeDetailState?.spec_confirmed === true}
                    />
                  ) : undefined
                }
              />
              {showAcceptReview ? (
                <div className={styles.acceptReviewBar} data-testid="accept-review-bar">
                  {acceptReviewError ? (
                    <div
                      id="accept-review-error"
                      className={styles.acceptReviewError}
                      data-testid="accept-review-error"
                      role="alert"
                    >
                      {acceptReviewError}
                    </div>
                  ) : null}
                  <div className={styles.acceptReviewControls}>
                    <input
                      ref={reviewInputRef}
                      type="text"
                      className={styles.acceptReviewInput}
                      placeholder="Review summary..."
                      value={reviewSummaryDraft}
                      aria-invalid={acceptReviewError ? 'true' : 'false'}
                      aria-describedby={acceptReviewError ? 'accept-review-error' : undefined}
                      onChange={(event) => {
                        setReviewSummaryDraft(event.target.value)
                        if (acceptReviewError) {
                          setAcceptReviewError(null)
                        }
                      }}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault()
                          void handleAcceptReview()
                        }
                      }}
                      disabled={isAccepting}
                    />
                    <button
                      type="button"
                      className={styles.acceptReviewButton}
                      disabled={isAccepting || !reviewSummaryDraft.trim()}
                      onClick={() => void handleAcceptReview()}
                      data-testid="accept-review-button"
                    >
                      {isAccepting ? 'Accepting...' : 'Accept Review'}
                    </button>
                  </div>
                </div>
              ) : null}
              <ComposerBar
                onSend={(content) => {
                  void sendTurn(content)
                }}
                disabled={composerDisabled}
              />
            </>
          </div>
        </div>
      </div>

      {!isReviewNode ? (
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
      ) : null}
    </div>
  )
}
