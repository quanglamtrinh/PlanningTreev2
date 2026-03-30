import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import type { ThreadRole } from '../../api/types'
import { useChatStore } from '../../stores/chat-store'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useProjectStore } from '../../stores/project-store'
import {
  buildChatV2Url,
  buildLegacyChatUrl,
  isExecutionAuditV2SurfaceEnabled,
  parseThreadTab,
  resolveLegacyRouteTarget,
  type ThreadTab,
} from '../conversation/surfaceRouting'
import { NodeDetailCard } from '../node/NodeDetailCard'
import { ComposerBar } from './ComposerBar'
import { FrameContextFeedBlock } from './FrameContextFeedBlock'
import { MessageFeed } from './MessageFeed'
import styles from './BreadcrumbChatView.module.css'

function isThreadComposerReadOnly(
  threadRole: ThreadRole,
  shapingFrozen: boolean,
  auditWritable: boolean,
): boolean {
  switch (threadRole) {
    case 'ask_planning':
      return shapingFrozen
    case 'execution':
      return false
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

export function BreadcrumbChatView() {
  const navigate = useNavigate()
  const { projectId, nodeId } = useParams<{ projectId: string; nodeId: string }>()
  const [searchParams] = useSearchParams()
  const detailStateKey = projectId && nodeId ? `${projectId}::${nodeId}` : ''
  const lastRouteSelectionSyncRef = useRef<string | null>(null)

  const { session, isLoading, isSending, error, loadSession, sendMessage, disconnect } = useChatStore(
    useShallow((s) => ({
      session: s.session,
      isLoading: s.isLoading,
      isSending: s.isSending,
      error: s.error,
      loadSession: s.loadSession,
      sendMessage: s.sendMessage,
      disconnect: s.disconnect,
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
    const node = snapshot.tree_state.node_registry.find((n) => n.node_id === nodeId)
    return node?.node_kind === 'review'
  }, [projectId, nodeId, snapshot])

  const requestedThreadTab = parseThreadTab(searchParams.get('thread'))
  const executionAuditV2Enabled = isExecutionAuditV2SurfaceEnabled(bootstrap)
  const routeTarget = resolveLegacyRouteTarget({
    requestedThreadTab,
    isReviewNode,
    executionAuditV2Enabled,
  })
  const threadTab: ThreadTab = routeTarget.threadTab
  const threadRole: ThreadRole = resolveThreadRole(isReviewNode, threadTab)
  const shouldRedirectToV2 = routeTarget.surface === 'v2'
  const shouldCanonicalizeLegacy =
    routeTarget.surface === 'legacy' && requestedThreadTab !== routeTarget.threadTab
  const hasRouteNode =
    Boolean(snapshot && projectId && snapshot.project.id === projectId && nodeId) &&
    snapshot!.tree_state.node_registry.some((node) => node.node_id === nodeId)

  useEffect(() => {
    if (!projectId || !nodeId) {
      return
    }
    if (!snapshot || snapshot.project.id !== projectId) {
      return
    }
    if (shouldRedirectToV2 && threadTab !== 'ask') {
      void navigate(buildChatV2Url(projectId, nodeId, threadTab), { replace: true })
      return
    }
    if (shouldCanonicalizeLegacy) {
      void navigate(buildLegacyChatUrl(projectId, nodeId, threadTab), { replace: true })
    }
  }, [
    navigate,
    nodeId,
    projectId,
    shouldCanonicalizeLegacy,
    shouldRedirectToV2,
    snapshot,
    threadTab,
  ])

  useEffect(() => {
    if (
      !projectId ||
      !nodeId ||
      !hasRouteNode ||
      !snapshot ||
      snapshot.project.id !== projectId ||
      shouldRedirectToV2 ||
      shouldCanonicalizeLegacy
    ) {
      return
    }
    void loadSession(projectId, nodeId, threadRole)
  }, [
    hasRouteNode,
    loadSession,
    nodeId,
    projectId,
    shouldCanonicalizeLegacy,
    shouldRedirectToV2,
    snapshot,
    threadRole,
  ])

  useEffect(() => () => {
    disconnect()
  }, [disconnect])

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
  }, [projectId, snapshot?.project.id, isLoadingSnapshot, activeProjectId, projectError, loadProject])

  const detailNode = useMemo(() => {
    if (!projectId || !nodeId || !snapshot || snapshot.project.id !== projectId) {
      return null
    }
    return snapshot.tree_state.node_registry.find((node) => node.node_id === nodeId) ?? null
  }, [projectId, nodeId, snapshot])

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
  }, [projectId, nodeId, detailNode, snapshot, selectedNodeId, selectNode])

  useEffect(() => {
    if (!projectId || !nodeId || !detailNode || !snapshot || snapshot.project.id !== projectId) {
      return
    }
    void loadDetailState(projectId, nodeId).catch(() => undefined)
  }, [projectId, nodeId, detailNode, snapshot, loadDetailState])

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
  }, [projectId, nodeId, snapshot, detailNode, isLoadingSnapshot, activeProjectId, projectError])

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
  }, [projectId, nodeId, detailCardState, projectError, activeProjectId, snapshot, detailNode])

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
  }, [showAcceptReview, nodeId, projectId])

  const handleAcceptReview = useCallback(async () => {
    const summary = reviewSummaryDraft.trim()
    if (!summary || !projectId || !nodeId) return
    setIsAccepting(true)
    setAcceptReviewError(null)
    try {
      const activatedSiblingId = await acceptLocalReviewAction(projectId, nodeId, summary)
      setReviewSummaryDraft('')
      setAcceptReviewError(null)
      if (activatedSiblingId) {
        void navigate(buildLegacyChatUrl(projectId, activatedSiblingId, 'ask'))
      }
    } catch (error) {
      setAcceptReviewError(error instanceof Error ? error.message : String(error))
      reviewInputRef.current?.focus()
    } finally {
      setIsAccepting(false)
    }
  }, [reviewSummaryDraft, projectId, nodeId, acceptLocalReviewAction, navigate])

  const isActiveTurn = !!session?.active_turn_id
  const shapingFrozen = nodeDetailState?.shaping_frozen ?? (detailNode?.workflow?.shaping_frozen === true)
  const auditWritable = nodeDetailState?.audit_writable === true
  const threadReadOnly = useMemo(
    () => isThreadComposerReadOnly(threadRole, shapingFrozen, auditWritable),
    [threadRole, shapingFrozen, auditWritable],
  )
  const composerDisabled = threadReadOnly || isActiveTurn || isSending || isLoading || !session

  return (
    <div className={styles.root}>
      <div
        className={`${styles.threadPane} ${isReviewNode ? styles.threadPaneSolo : ''}`}
        data-testid="breadcrumb-thread-pane"
      >
        <div className={styles.threadSurface}>
          {isReviewNode ? (
            <div className={styles.threadTabBar} data-testid="breadcrumb-review-audit-header">
              <span className={`${styles.threadTab} ${styles.threadTabActive}`} data-testid="breadcrumb-thread-tab-review-audit">
                Review Audit
              </span>
            </div>
          ) : (
            <nav className={styles.threadTabBar} role="tablist" aria-label="Thread mode">
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
                    void navigate(
                      executionAuditV2Enabled
                        ? buildChatV2Url(projectId, nodeId, 'execution')
                        : buildLegacyChatUrl(projectId, nodeId, 'execution'),
                    )
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
                    void navigate(
                      executionAuditV2Enabled
                        ? buildChatV2Url(projectId, nodeId, 'audit')
                        : buildLegacyChatUrl(projectId, nodeId, 'audit'),
                    )
                  }
                }}
              >
                Audit
              </button>
            </nav>
          )}

          <div className={styles.threadTabBody}>
            <>
              {error && (
                <div className={styles.errorBanner}>
                  {error}
                </div>
              )}
              <MessageFeed
                messages={session?.messages ?? []}
                isLoading={isLoading}
                prefix={
                  (threadTab === 'ask' || threadTab === 'audit') && !isReviewNode && snapshot && projectId && nodeId
                    ? (
                        <FrameContextFeedBlock
                          projectId={projectId}
                          nodeId={nodeId}
                          nodeRegistry={snapshot.tree_state.node_registry}
                          variant={threadTab === 'audit' ? 'audit' : 'ask'}
                          specConfirmed={nodeDetailState?.spec_confirmed === true}
                        />
                      )
                    : undefined
                }
              />
              {showAcceptReview && (
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
                      onChange={(e) => {
                        setReviewSummaryDraft(e.target.value)
                        if (acceptReviewError) {
                          setAcceptReviewError(null)
                        }
                      }}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
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
              )}
              <ComposerBar
                onSend={sendMessage}
                disabled={composerDisabled}
              />
            </>
          </div>
        </div>
      </div>

      {!isReviewNode && (
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
      )}
    </div>
  )
}
