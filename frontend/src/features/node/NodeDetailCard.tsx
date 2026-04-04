import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { NodeRecord } from '../../api/types'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { ClarifyPanel } from './ClarifyPanel'
import { NodeDescribePanel } from './NodeDescribePanel'
import { NodeDocumentEditor, type FramePostUpdateBranch } from './NodeDocumentEditor'
import { SplitPanel } from './SplitPanel'
import { NodeStatusBadge } from './NodeStatusBadge'
import { ReviewDetailPanel } from './ReviewDetailPanel'
import { BreadcrumbDetailTabs, breadcrumbActiveTabLabelId } from './BreadcrumbDetailTabs'
import { WorkflowStepper } from './WorkflowStepper'
import type { WorkflowTab } from './WorkflowStepper'
import styles from './NodeDetailCard.module.css'

type DetailTab = WorkflowTab

type NodeDetailCardState = 'ready' | 'loading' | 'unavailable'

type Props = {
  projectId: string | null
  node: NodeRecord | null
  variant: 'graph' | 'breadcrumb'
  showClose: boolean
  onClose?: () => void
  state?: NodeDetailCardState
  message?: string | null
}

function deriveDetailTab(activeStep: 'frame' | 'clarify' | 'spec', frameBranchReady?: boolean): DetailTab {
  if (frameBranchReady) {
    return 'frame_updated'
  }
  return activeStep
}

function resolveRequestedDetailTab(
  requestedTab: DetailTab,
  detailState?: {
    active_step: 'frame' | 'clarify' | 'spec'
    frame_branch_ready?: boolean
  },
): DetailTab {
  if (requestedTab !== 'frame_updated') {
    return requestedTab
  }
  if (detailState?.frame_branch_ready) {
    return 'frame_updated'
  }
  return detailState?.active_step ?? 'frame'
}

const FRAME_POST_UPDATE_STORAGE = 'planningtree:framePostUpdate:'

function framePostUpdateStorageKey(projectId: string, nodeId: string) {
  return `${FRAME_POST_UPDATE_STORAGE}${projectId}:${nodeId}`
}

/** Breadcrumb: same grey toolbar as document editor; no save line for non-document panels */
function BreadcrumbNonDocToolbar({ tabs, children }: { tabs: ReactNode; children: ReactNode }) {
  return (
    <>
      <div className={`${styles.documentStatusRow} ${styles.documentStatusRowEmbedTabs}`}>{tabs}</div>
      {children}
    </>
  )
}

export function NodeDetailCard({
  projectId,
  node,
  variant,
  showClose,
  onClose,
  state = 'ready',
  message = null,
}: Props) {
  const [detailTab, setDetailTab] = useState<DetailTab>('frame')
  const [framePostUpdateBranch, setFramePostUpdateBranch] = useState<FramePostUpdateBranch>('none')
  const isReviewNode = node?.node_kind === 'review'

  const detailStateKey = projectId && node ? `${projectId}::${node.node_id}` : ''
  const detailState = useDetailStateStore((s) => (detailStateKey ? s.entries[detailStateKey] : undefined))
  const detailStateError = useDetailStateStore((s) => (detailStateKey ? s.errors[detailStateKey] : undefined))
  const loadDetailState = useDetailStateStore((s) => s.loadDetailState)
  const resetWorkspaceAction = useDetailStateStore((s) => s.resetWorkspace)
  const isResettingWorkspace = useDetailStateStore((s) =>
    detailStateKey ? (s.resettingWorkspace[detailStateKey] ?? false) : false,
  )

  useEffect(() => {
    setDetailTab('frame')
  }, [node?.node_id, state])

  useEffect(() => {
    if (!projectId || !node) {
      return
    }
    const raw = sessionStorage.getItem(framePostUpdateStorageKey(projectId, node.node_id))
    if (raw === 'spec' || raw === 'split') {
      setFramePostUpdateBranch(raw)
    } else {
      setFramePostUpdateBranch('none')
    }
  }, [projectId, node?.node_id])

  useEffect(() => {
    if (!detailState || !projectId || !node) {
      return
    }
    if (detailState.frame_needs_reconfirm && framePostUpdateBranch !== 'none') {
      sessionStorage.removeItem(framePostUpdateStorageKey(projectId, node.node_id))
      setFramePostUpdateBranch('none')
    }
  }, [detailState?.frame_needs_reconfirm, framePostUpdateBranch, projectId, node])

  useEffect(() => {
    if (projectId && node && state === 'ready') {
      void loadDetailState(projectId, node.node_id)
    }
  }, [projectId, node?.node_id, state, loadDetailState])

  useEffect(() => {
    if (detailState?.active_step) {
      const nextTab = deriveDetailTab(detailState.active_step, detailState.frame_branch_ready)
      setDetailTab((currentTab) => {
        if (currentTab === 'split' && (nextTab === 'frame_updated' || nextTab === 'spec')) {
          return currentTab
        }
        // Stay on Frame updated (frame.md) while the workflow suggests Spec (spec.md).
        if (currentTab === 'frame_updated' && nextTab === 'spec' && framePostUpdateBranch !== 'spec') {
          return currentTab
        }
        // Stay on Clarify after the user confirms — answered questions remain visible.
        // The user can navigate to Spec manually via the tab bar.
        if (currentTab === 'clarify' && nextTab === 'spec') {
          return currentTab
        }
        return nextTab
      })
    }
  }, [detailState?.active_step, detailState?.frame_branch_ready, framePostUpdateBranch])

  const splitTabBlocked = framePostUpdateBranch === 'spec'
  const specTabBlocked = framePostUpdateBranch === 'split'

  const commitFramePostUpdate = useCallback(
    (branch: 'spec' | 'split') => {
      if (!projectId || !node) {
        return
      }
      sessionStorage.setItem(framePostUpdateStorageKey(projectId, node.node_id), branch)
      setFramePostUpdateBranch(branch)
    },
    [projectId, node],
  )

  const workflowTabDisabled = useMemo(
    () => ({
      split: splitTabBlocked,
      spec: specTabBlocked,
      finish: specTabBlocked,
    }),
    [specTabBlocked, splitTabBlocked],
  )

  const handleTabChange = useCallback(
    (nextTab: DetailTab) => {
      if (nextTab === 'split' && splitTabBlocked) {
        return
      }
      if (nextTab === 'spec' && specTabBlocked) {
        return
      }
      setDetailTab(resolveRequestedDetailTab(nextTab, detailState))
    },
    [detailState, specTabBlocked, splitTabBlocked],
  )

  const showDetailStateError =
    Boolean(detailStateError) && (variant !== 'breadcrumb' || !detailState)
  const showGitBlockerBanner =
    detailTab === 'spec' &&
    detailState?.git_ready === false &&
    Boolean(detailState.git_blocker_message)

  const rootClassName = useMemo(
    () =>
      `${styles.card} ${variant === 'breadcrumb' ? styles.cardBreadcrumb : styles.cardGraph}`,
    [variant],
  )

  if (state !== 'ready' || !node || !projectId) {
    return (
      <section
        className={rootClassName}
        data-testid={`${variant}-node-detail-card`}
        data-variant={variant}
      >
        <div className={styles.unavailableState}>
          <p className={styles.unavailableEyebrow}>
            {state === 'loading' ? 'Loading detail' : 'Node unavailable'}
          </p>
          <h3 className={styles.unavailableTitle}>
            {state === 'loading' ? 'Loading node details' : 'Node details unavailable'}
          </h3>
          <p className={styles.unavailableBody}>
            {message ??
              (state === 'loading'
                ? 'The node snapshot is loading for this breadcrumb route.'
                : 'This route does not map to a node in the current project snapshot.')}
          </p>
        </div>
      </section>
    )
  }

  const breadcrumbPanelId = 'breadcrumb-node-detail-panel'

  const breadcrumbTabsEmbedded =
    variant === 'breadcrumb' ? (
      <BreadcrumbDetailTabs
        embedded
        detailTab={detailTab}
        detailState={detailState}
        onTabChange={handleTabChange}
        tabDisabled={workflowTabDisabled}
        panelId={breadcrumbPanelId}
      />
    ) : null

  const detailPanelsFragment = !isReviewNode ? (
    <>
      {detailTab === 'describe' ? (
        breadcrumbTabsEmbedded ? (
          <BreadcrumbNonDocToolbar tabs={breadcrumbTabsEmbedded}>
            <div className={styles.cardBodyAux}>
              <NodeDescribePanel
                node={node}
                projectId={projectId}
                detailState={detailState}
                isResetting={isResettingWorkspace}
                onResetToBefore={() => void resetWorkspaceAction(projectId, node.node_id, 'initial')}
                onResetToResult={() => void resetWorkspaceAction(projectId, node.node_id, 'head')}
              />
            </div>
          </BreadcrumbNonDocToolbar>
        ) : (
          <div className={styles.cardBodyAux}>
            <NodeDescribePanel
              node={node}
              projectId={projectId}
              detailState={detailState}
              isResetting={isResettingWorkspace}
              onResetToBefore={() => void resetWorkspaceAction(projectId, node.node_id, 'initial')}
              onResetToResult={() => void resetWorkspaceAction(projectId, node.node_id, 'head')}
            />
          </div>
        )
      ) : null}

      {detailTab === 'frame' || detailTab === 'frame_updated' ? (
        <div className={styles.documentTabStack}>
          <NodeDocumentEditor
            projectId={projectId}
            node={node}
            kind="frame"
            workflowTab={detailTab}
            onWorkflowTabChange={handleTabChange}
            onConfirm="workflow"
            readOnly={detailState?.frame_read_only}
            framePostUpdateBranch={framePostUpdateBranch}
            onFramePostUpdateCommit={commitFramePostUpdate}
            documentToolbarTabs={breadcrumbTabsEmbedded ?? undefined}
          />
        </div>
      ) : null}

      {detailTab === 'clarify' ? (
        breadcrumbTabsEmbedded ? (
          <BreadcrumbNonDocToolbar tabs={breadcrumbTabsEmbedded}>
            <ClarifyPanel
              projectId={projectId}
              node={node}
              readOnly={detailState?.clarify_read_only}
            />
          </BreadcrumbNonDocToolbar>
        ) : (
          <ClarifyPanel
            projectId={projectId}
            node={node}
            readOnly={detailState?.clarify_read_only}
          />
        )
      ) : null}

      {detailTab === 'split' ? (
        breadcrumbTabsEmbedded ? (
          <BreadcrumbNonDocToolbar tabs={breadcrumbTabsEmbedded}>
            <div className={styles.cardBodyAux}>
              <SplitPanel projectId={projectId} node={node} detailState={detailState} />
            </div>
          </BreadcrumbNonDocToolbar>
        ) : (
          <div className={styles.cardBodyAux}>
            <SplitPanel projectId={projectId} node={node} detailState={detailState} />
          </div>
        )
      ) : null}

      {detailTab === 'spec' ? (
        <div className={styles.documentTabStack}>
          {detailState?.spec_stale ? (
            <div className={styles.staleBanner} data-testid="stale-banner-spec" role="status">
              Frame was updated since spec was last reviewed.
            </div>
          ) : null}
          <NodeDocumentEditor
            projectId={projectId}
            node={node}
            kind="spec"
            workflowTab="spec"
            onConfirm="workflow"
            readOnly={detailState?.spec_read_only}
            documentToolbarTabs={breadcrumbTabsEmbedded ?? undefined}
          />
        </div>
      ) : null}
    </>
  ) : null

  return (
    <section
      className={rootClassName}
      data-testid={`${variant}-node-detail-card`}
      data-variant={variant}
    >
      <div className={styles.cardHeader}>
        <div className={styles.cardHeaderTop}>
          <div className={styles.nodeTitleBlock}>
            <div className={styles.nodeMetaRow}>
              <span className={styles.nodeHier}>{node.hierarchical_number}</span>
              <NodeStatusBadge status={node.status} />
            </div>
            <h2 className={styles.nodeHeading}>{node.title}</h2>
          </div>
          <div className={styles.cardHeaderActions}>
            {showClose ? (
              <button
                type="button"
                className={styles.closeButton}
                onClick={onClose}
                aria-label="Close detail panel"
              >
                <span aria-hidden="true">x</span>
              </button>
            ) : null}
          </div>
        </div>

        {!isReviewNode ? (
          <div className={styles.explorationRegion} role="region" aria-label="Task exploration steps">
            <WorkflowStepper
              detailTab={detailTab}
              detailState={detailState}
              onTabChange={handleTabChange}
              tabDisabled={workflowTabDisabled}
              readOnly={variant === 'breadcrumb'}
            />
          </div>
        ) : null}
      </div>

      <div className={styles.cardBody}>
        {showDetailStateError ? (
          <div className={styles.detailStateError}>
            <p className={styles.body}>Failed to load detail state: {detailStateError}</p>
            <button
              type="button"
              className={styles.retryButton}
              onClick={() => {
                if (projectId && node) void loadDetailState(projectId, node.node_id)
              }}
            >
              Retry
            </button>
          </div>
        ) : null}

        {detailState?.workflow_notice ? (
          <div className={styles.workflowNoticeBanner} data-testid="workflow-notice" role="status">
            {detailState.workflow_notice}
          </div>
        ) : null}

        {!isReviewNode && detailState?.package_audit_ready ? (
          <div
            className={styles.packageAuditReadyBanner}
            data-testid="package-audit-ready-banner"
            role="status"
          >
            Package audit ready. The accepted rollup package is now available in the Audit thread for
            this task.
          </div>
        ) : null}

        {showGitBlockerBanner ? (
          <div className={styles.gitBlockerBanner} role="status">
            {detailState.git_blocker_message}
          </div>
        ) : null}

        {isReviewNode ? <ReviewDetailPanel projectId={projectId} node={node} /> : null}

        {!isReviewNode && variant === 'breadcrumb' ? (
          <div
            id={breadcrumbPanelId}
            role="tabpanel"
            aria-labelledby={breadcrumbActiveTabLabelId(detailTab)}
            className={styles.breadcrumbTabPanel}
          >
            {detailPanelsFragment}
          </div>
        ) : null}

        {!isReviewNode && variant !== 'breadcrumb' ? detailPanelsFragment : null}
      </div>
    </section>
  )
}
