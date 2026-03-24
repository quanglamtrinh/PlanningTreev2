import { Fragment, useEffect, useMemo, useState } from 'react'
import type { NodeRecord } from '../../api/types'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { ClarifyPanel } from './ClarifyPanel'
import { NodeDescribePanel } from './NodeDescribePanel'
import { NodeDocumentEditor } from './NodeDocumentEditor'
import { ExecutionStatusBadge } from './ExecutionStatusBadge'
import { NodeStatusBadge } from './NodeStatusBadge'
import styles from './NodeDetailCard.module.css'

type DetailTab = 'describe' | 'frame' | 'clarify' | 'spec'

const DETAIL_STEPS: { id: DetailTab; label: string }[] = [
  { id: 'describe', label: 'Describe' },
  { id: 'frame', label: 'Frame' },
  { id: 'clarify', label: 'Clarify' },
  { id: 'spec', label: 'Spec' },
]

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

  const detailStateKey = projectId && node ? `${projectId}::${node.node_id}` : ''
  const detailState = useDetailStateStore((s) => (detailStateKey ? s.entries[detailStateKey] : undefined))
  const detailStateError = useDetailStateStore((s) => (detailStateKey ? s.errors[detailStateKey] : undefined))
  const loadDetailState = useDetailStateStore((s) => s.loadDetailState)
  const finishTaskAction = useDetailStateStore((s) => s.finishTask)
  const resetWorkspaceAction = useDetailStateStore((s) => s.resetWorkspace)
  const isFinishingTask = useDetailStateStore((s) =>
    detailStateKey ? (s.finishingTask[detailStateKey] ?? false) : false,
  )
  const isResettingWorkspace = useDetailStateStore((s) =>
    detailStateKey ? (s.resettingWorkspace[detailStateKey] ?? false) : false,
  )

  // Reset to frame on node change
  useEffect(() => {
    setDetailTab('frame')
  }, [node?.node_id, state])

  useEffect(() => {
    if (projectId && node && state === 'ready') {
      void loadDetailState(projectId, node.node_id)
    }
  }, [projectId, node?.node_id, state, loadDetailState])

  // Auto-follow active_step from backend
  useEffect(() => {
    if (detailState?.active_step) setDetailTab(detailState.active_step)
  }, [detailState?.active_step])

  const rootClassName = useMemo(
    () =>
      `${styles.card} ${variant === 'breadcrumb' ? styles.cardBreadcrumb : styles.cardGraph}`,
    [variant],
  )

  const activeStepIndex = useMemo(
    () => DETAIL_STEPS.findIndex((s) => s.id === detailTab),
    [detailTab],
  )

  const isStepConfirmed = (stepId: DetailTab): boolean => {
    if (!detailState) return false
    if (stepId === 'describe') return false
    if (stepId === 'frame') return detailState.frame_confirmed
    if (stepId === 'clarify') return detailState.clarify_confirmed
    if (stepId === 'spec') return detailState.spec_confirmed
    return false
  }

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

  return (
    <section
      className={rootClassName}
      data-testid={`${variant}-node-detail-card`}
      data-variant={variant}
    >
      <div className={styles.cardHeader}>
        <div className={styles.cardHeaderTop}>
          <div className={styles.nodeTitleBlock}>
            <p className={styles.nodeEyebrow}>Task</p>
            <div className={styles.nodeTitleRow}>
              <span className={styles.nodeHier}>{node.hierarchical_number}</span>
              <h2 className={styles.nodeHeading}>{node.title}</h2>
              <NodeStatusBadge status={node.status} />
              <ExecutionStatusBadge
                status={detailState?.execution_status}
                className={styles.executionStatusBadge}
              />
            </div>
          </div>
          <div className={styles.cardHeaderActions}>
            <button
              type="button"
              className={styles.finishTaskButton}
              disabled={
                !detailState ||
                detailState.can_finish_task !== true ||
                detailState.git_ready === false ||
                isFinishingTask
              }
              title={
                detailState?.git_ready === false && detailState.git_blocker_message
                  ? detailState.git_blocker_message
                  : detailState?.can_finish_task !== true
                    ? 'Complete and confirm the spec, then satisfy Git prerequisites to finish this task.'
                    : 'Run execution for this task'
              }
              onClick={() => void finishTaskAction(projectId, node.node_id)}
            >
              {isFinishingTask ? 'Finishing…' : 'Finish Task'}
            </button>
            {showClose ? (
              <button
                type="button"
                className={styles.closeButton}
                onClick={onClose}
                aria-label="Close detail panel"
              >
                <span aria-hidden="true">×</span>
              </button>
            ) : null}
          </div>
        </div>

        <div className={styles.explorationRegion} role="region" aria-label="Task exploration steps">
          <nav className={styles.stepper} aria-label="Describe, Frame, Clarify, Spec">
            {DETAIL_STEPS.map((step, idx) => {
              const isActive = detailTab === step.id
              const confirmed = isStepConfirmed(step.id)
              const isDescribe = step.id === 'describe'
              const arrowBold = idx > 0 && idx <= activeStepIndex
              return (
                <Fragment key={step.id}>
                  {idx > 0 && (
                    <span
                      className={`${styles.stepArrow} ${arrowBold ? styles.stepArrowBold : ''}`}
                      aria-hidden="true"
                    >
                      {'>'}
                    </span>
                  )}
                  <button
                    type="button"
                    className={[
                      styles.stepButton,
                      isDescribe ? styles.stepButtonDescribe : '',
                      confirmed ? styles.stepButtonDone : '',
                      isActive ? styles.stepButtonActive : '',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    onClick={() => setDetailTab(step.id)}
                    aria-label={step.label}
                    aria-current={isActive ? 'step' : undefined}
                  >
                    <span>{step.label}</span>
                    {confirmed ? (
                      <span className={styles.stepDoneTick} aria-hidden="true">
                        ✓
                      </span>
                    ) : null}
                  </button>
                </Fragment>
              )
            })}
          </nav>
        </div>
      </div>

      <div className={styles.cardBody}>
        {detailStateError ? (
          <div className={styles.detailStateError}>
            <p className={styles.body}>Failed to load detail state: {detailStateError}</p>
            <button
              type="button"
              className={styles.retryButton}
              onClick={() => { if (projectId && node) void loadDetailState(projectId, node.node_id) }}
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

        {detailState?.generation_error ? (
          <div className={styles.workflowErrorBanner} data-testid="generation-error-banner" role="alert">
            Spec generation did not start: {detailState.generation_error}. You can retry from the Spec tab.
          </div>
        ) : null}

        {detailState?.git_ready === false && detailState.git_blocker_message ? (
          <div className={styles.gitBlockerBanner} role="status">
            {detailState.git_blocker_message}
          </div>
        ) : null}

        {detailTab === 'describe' && (
          <div className={styles.cardBodyAux}>
            <NodeDescribePanel
              node={node}
              projectId={projectId}
              detailState={detailState}
              isResetting={isResettingWorkspace}
              onResetToBefore={() =>
                void resetWorkspaceAction(projectId, node.node_id, 'initial')
              }
              onResetToResult={() => void resetWorkspaceAction(projectId, node.node_id, 'head')}
            />
          </div>
        )}

        {detailTab === 'frame' && (
          <div className={styles.documentTabStack}>
            <NodeDocumentEditor
              projectId={projectId}
              node={node}
              kind="frame"
              onConfirm="workflow"
              readOnly={detailState?.frame_read_only}
            />
          </div>
        )}

        {detailTab === 'clarify' && (
          <ClarifyPanel
            projectId={projectId}
            node={node}
            readOnly={detailState?.clarify_read_only}
          />
        )}

        {detailTab === 'spec' && (
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
              onConfirm="workflow"
              readOnly={detailState?.spec_read_only}
            />
          </div>
        )}
      </div>
    </section>
  )
}
