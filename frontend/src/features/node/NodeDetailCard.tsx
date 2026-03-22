import { Fragment, useCallback, useEffect, useMemo, useState } from 'react'
import type { NodeRecord } from '../../api/types'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { ClarifyPanel } from './ClarifyPanel'
import { NodeDescribePanel } from './NodeDescribePanel'
import { NodeDocumentEditor } from './NodeDocumentEditor'
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
  const detailState = useDetailStateStore((s) => detailStateKey ? s.entries[detailStateKey] : undefined)
  const detailStateError = useDetailStateStore((s) => detailStateKey ? s.errors[detailStateKey] : undefined)
  const loadDetailState = useDetailStateStore((s) => s.loadDetailState)

  useEffect(() => {
    setDetailTab('frame')
  }, [node?.node_id, state])

  useEffect(() => {
    if (projectId && node && state === 'ready') {
      void loadDetailState(projectId, node.node_id)
    }
  }, [projectId, node?.node_id, state, loadDetailState])

  const isTabLocked = useCallback(
    (tabId: DetailTab): boolean => {
      if (tabId === 'describe' || tabId === 'frame') return false
      // If detail state failed to load, don't lock — let the error banner handle it
      if (detailStateError) return false
      if (!detailState) return true
      if (tabId === 'clarify') return !detailState.clarify_unlocked
      if (tabId === 'spec') return !detailState.spec_unlocked
      return false
    },
    [detailState, detailStateError],
  )

  const explorationLockHint = useMemo(() => {
    if (detailStateError) return null
    if (!detailState) {
      return 'Loading workflow state…'
    }
    if (!detailState.clarify_unlocked) {
      return 'Confirm Frame to unlock Clarify.'
    }
    if (!detailState.spec_unlocked) {
      return 'Complete Clarify to unlock Spec.'
    }
    return null
  }, [detailState, detailStateError])

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
            </div>
          </div>
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

        <div className={styles.explorationRegion} role="region" aria-label="Task exploration steps">
          <nav className={styles.stepper} aria-label="Describe, Frame, Clarify, Spec">
            {DETAIL_STEPS.map((step, idx) => {
              const locked = isTabLocked(step.id)
              return (
                <Fragment key={step.id}>
                  {idx > 0 && (
                    <span className={styles.stepArrow} aria-hidden="true">
                      {'>'}
                    </span>
                  )}
                  <button
                    type="button"
                    className={`${styles.stepButton} ${detailTab === step.id ? styles.stepButtonActive : ''} ${locked ? styles.stepButtonLocked : ''}`}
                    onClick={() => {
                      if (!locked) setDetailTab(step.id)
                    }}
                    disabled={locked}
                    aria-label={locked ? `${step.label} (locked)` : step.label}
                    aria-current={detailTab === step.id ? 'step' : undefined}
                    aria-describedby={
                      locked && explorationLockHint ? 'exploration-lock-hint' : undefined
                    }
                  >
                    {step.label}
                  </button>
                </Fragment>
              )
            })}
          </nav>
          {explorationLockHint ? (
            <p id="exploration-lock-hint" className={styles.explorationLockHint}>
              {explorationLockHint}
            </p>
          ) : null}
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
        {detailTab === 'describe' && (
          <div className={variant === 'graph' ? styles.cardBodyAux : undefined}>
            <NodeDescribePanel node={node} />
          </div>
        )}

        {detailTab === 'frame' && (
          <div className={styles.documentTabStack}>
            <NodeDocumentEditor
              projectId={projectId}
              node={node}
              kind="frame"
              onConfirm="workflow"
            />
          </div>
        )}

        {detailTab === 'clarify' && (
          <>
            {detailState?.clarify_stale ? (
              <div className={styles.staleBanner} data-testid="stale-banner-clarify" role="status">
                Frame was updated since clarify was seeded. Review questions for accuracy.
              </div>
            ) : null}
            <ClarifyPanel projectId={projectId} node={node} />
          </>
        )}

        {detailTab === 'spec' && (
          <div className={styles.documentTabStack}>
            {detailState?.spec_stale ? (
              <div className={styles.staleBanner} data-testid="stale-banner-spec" role="status">
                Frame or Clarify was updated since spec was last reviewed.
              </div>
            ) : null}
            <NodeDocumentEditor
              projectId={projectId}
              node={node}
              kind="spec"
              onConfirm="workflow"
            />
          </div>
        )}
      </div>
    </section>
  )
}
