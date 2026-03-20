import { Fragment, useEffect, useMemo, useState } from 'react'
import type { NodeRecord } from '../../api/types'
import { ClarifyMockPanel } from '../graph/ClarifyMockPanel'
import styles from './NodeDetailCard.module.css'

type DetailTab = 'frame' | 'clarify' | 'spec'

const DETAIL_STEPS: { id: DetailTab; label: string }[] = [
  { id: 'frame', label: 'Frame' },
  { id: 'clarify', label: 'Clarify' },
  { id: 'spec', label: 'Spec' },
]

type NodeDetailCardState = 'ready' | 'loading' | 'unavailable'

type Props = {
  node: NodeRecord | null
  variant: 'graph' | 'breadcrumb'
  showClose: boolean
  onClose?: () => void
  state?: NodeDetailCardState
  message?: string | null
}

export function NodeDetailCard({
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

  if (state !== 'ready' || !node) {
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
        {detailTab === 'frame' && (
          <div className={styles.contentPanel}>
            <p className={styles.eyebrow}>
              {node.hierarchical_number ? `${node.hierarchical_number} - Node` : 'Node'}
            </p>
            <h3 className={styles.title}>{node.title}</h3>
            <p className={styles.body}>{node.description.trim() || 'No description yet.'}</p>
            <p className={styles.body}>
              Status: <strong>{node.status}</strong> . Children: {node.child_ids.length}
            </p>
          </div>
        )}

        {detailTab === 'clarify' && <ClarifyMockPanel />}

        {detailTab === 'spec' && (
          <div className={styles.contentPanel}>
            <p className={styles.eyebrow}>Spec</p>
            <p className={styles.title}>Specification</p>
            <p className={styles.body}>
              The specification document for <strong>{node.title}</strong> will appear here once
              generated.
            </p>
          </div>
        )}
      </div>
    </section>
  )
}
