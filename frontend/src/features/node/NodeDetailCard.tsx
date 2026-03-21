import { Fragment, useEffect, useMemo, useState } from 'react'
import type { NodeRecord } from '../../api/types'
import { ClarifyMockPanel } from '../graph/ClarifyMockPanel'
import { NodeDescribePanel } from './NodeDescribePanel'
import { NodeDocumentEditor } from './NodeDocumentEditor'
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

  useEffect(() => {
    setDetailTab('frame')
  }, [node?.node_id, state])

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
        <nav className={styles.stepper} aria-label="Detail steps">
          {DETAIL_STEPS.map((step, idx) => (
            <Fragment key={step.id}>
              {idx > 0 && (
                <span className={styles.stepArrow} aria-hidden="true">
                  {'>'}
                </span>
              )}
              <button
                type="button"
                className={`${styles.stepButton} ${detailTab === step.id ? styles.stepButtonActive : ''}`}
                onClick={() => setDetailTab(step.id)}
              >
                {step.label}
              </button>
            </Fragment>
          ))}
        </nav>
        {showClose ? (
          <button
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label="Close detail panel"
            title="Close"
          >
            x
          </button>
        ) : null}
      </div>

      <div className={styles.cardBody}>
        {detailTab === 'describe' && (
          <div className={variant === 'graph' ? styles.cardBodyAux : undefined}>
            <NodeDescribePanel node={node} />
          </div>
        )}

        {detailTab === 'frame' && (
          <NodeDocumentEditor projectId={projectId} node={node} kind="frame" />
        )}

        {detailTab === 'clarify' && <ClarifyMockPanel />}

        {detailTab === 'spec' && (
          <NodeDocumentEditor projectId={projectId} node={node} kind="spec" />
        )}
      </div>
    </section>
  )
}
