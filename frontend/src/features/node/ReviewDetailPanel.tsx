import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from '../../api/client'
import type { NodeRecord, ReviewState, RollupStatus } from '../../api/types'
import { useDetailStateStore } from '../../stores/detail-state-store'
import {
  formatReviewChainLabel,
  parentHierarchicalNumberFromReviewNode,
} from '../../utils/reviewSiblingLabels'
import styles from './ReviewDetailPanel.module.css'

type Props = {
  projectId: string
  node: NodeRecord
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

function rollupStatusLabel(status: RollupStatus): string {
  switch (status) {
    case 'accepted':
      return 'Accepted'
    case 'ready':
      return 'Ready'
    case 'pending':
    default:
      return 'Pending'
  }
}

export function ReviewDetailPanel({ projectId, node }: Props) {
  const acceptRollupReview = useDetailStateStore((state) => state.acceptRollupReview)
  const [reviewState, setReviewState] = useState<ReviewState | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isAccepting, setIsAccepting] = useState(false)

  const loadReviewState = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const next = await api.getReviewState(projectId, node.node_id)
      setReviewState(next)
    } catch (nextError) {
      setError(toErrorMessage(nextError))
    } finally {
      setIsLoading(false)
    }
  }, [projectId, node.node_id])

  useEffect(() => {
    void loadReviewState()
  }, [loadReviewState])

  const rollup = reviewState?.rollup
  const draft = rollup?.draft
  const parentHierarchicalNumber = parentHierarchicalNumberFromReviewNode(node.hierarchical_number)
  const canAcceptRollup =
    rollup?.status === 'ready' && !!draft?.summary && !!draft?.sha && !isAccepting
  const siblingManifest = reviewState?.sibling_manifest ?? []
  const completedSiblings = siblingManifest.filter((sibling) => sibling.status === 'completed')
  const activeSibling = siblingManifest.find((sibling) => sibling.status === 'active') ?? null
  const pendingSiblings = siblingManifest.filter((sibling) => sibling.status === 'pending')

  const rollupSummary = useMemo(() => {
    if (!rollup) {
      return null
    }
    if (rollup.status === 'accepted') {
      return {
        heading: 'Accepted Rollup',
        summary: rollup.summary,
        sha: rollup.sha,
        timestamp: rollup.accepted_at,
      }
    }
    if (draft?.summary || draft?.sha) {
      return {
        heading: 'Draft Rollup',
        summary: draft?.summary ?? null,
        sha: draft?.sha ?? null,
        timestamp: draft?.generated_at ?? null,
      }
    }
    return null
  }, [draft?.generated_at, draft?.sha, draft?.summary, rollup])

  const handleAcceptRollup = useCallback(async () => {
    if (!canAcceptRollup) {
      return
    }
    setIsAccepting(true)
    setError(null)
    try {
      await acceptRollupReview(projectId, node.node_id)
      await loadReviewState()
    } catch (nextError) {
      setError(toErrorMessage(nextError))
    } finally {
      setIsAccepting(false)
    }
  }, [acceptRollupReview, canAcceptRollup, loadReviewState, node.node_id, projectId])

  if (isLoading) {
    return (
      <div className={styles.panel} data-testid="review-detail-panel">
        <div className={styles.emptyState}>Loading review state...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className={styles.panel} data-testid="review-detail-panel">
        <div className={styles.errorBanner} role="alert">
          Failed to load review state: {error}
        </div>
        <button type="button" className={styles.retryButton} onClick={() => void loadReviewState()}>
          Retry
        </button>
      </div>
    )
  }

  if (!reviewState) {
    return (
      <div className={styles.panel} data-testid="review-detail-panel">
        <div className={styles.emptyState}>No review state is available for this node yet.</div>
      </div>
    )
  }

  return (
    <div className={styles.panel} data-testid="review-detail-panel">
      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <p className={styles.sectionEyebrow}>Review Lifecycle</p>
            <h3 className={styles.sectionTitle}>Checkpoint Progress</h3>
          </div>
          <span
            className={`${styles.statusBadge} ${styles[`status${rollupStatusLabel(reviewState.rollup.status)}`]}`}
          >
            {rollupStatusLabel(reviewState.rollup.status)}
          </span>
        </div>
        {reviewState.checkpoints.length ? (
          <ol className={styles.list}>
            {reviewState.checkpoints.map((checkpoint) => (
              <li key={checkpoint.label} className={styles.listItem}>
                <div className={styles.listRow}>
                  <strong>{checkpoint.label}</strong>
                  <span className={styles.metaText}>{checkpoint.sha}</span>
                </div>
                {checkpoint.summary ? <p className={styles.bodyText}>{checkpoint.summary}</p> : null}
                <p className={styles.metaText}>
                  Accepted at {checkpoint.accepted_at}
                  {checkpoint.source_node_id ? ` from ${checkpoint.source_node_id}` : ''}
                </p>
              </li>
            ))}
          </ol>
        ) : (
          <div className={styles.emptyState}>No child checkpoints have been accepted yet.</div>
        )}
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <p className={styles.sectionEyebrow}>Sibling Flow</p>
            <h3 className={styles.sectionTitle}>Review Chain</h3>
          </div>
          <span className={styles.metricPill}>{siblingManifest.length} tracked</span>
        </div>
        <div className={styles.manifestGroups}>
          <div className={styles.manifestGroup}>
            <div className={styles.manifestGroupHeader}>
              <h4 className={styles.manifestGroupTitle}>Completed siblings</h4>
              <span className={styles.metricPill}>{completedSiblings.length}</span>
            </div>
            {completedSiblings.length ? (
              <ul className={styles.list}>
                {completedSiblings.map((sibling) => (
                  <li key={sibling.index} className={styles.listItem}>
                    <div className={styles.listRow}>
                      <strong>
                        {formatReviewChainLabel(parentHierarchicalNumber, sibling.index)} {sibling.title}
                      </strong>
                      <span className={styles.metaText}>Completed</span>
                    </div>
                    {sibling.objective ? <p className={styles.bodyText}>{sibling.objective}</p> : null}
                    <p className={styles.metaText}>
                      Accepted as {sibling.checkpoint_label ?? 'checkpoint'}
                      {sibling.materialized_node_id ? ` from ${sibling.materialized_node_id}` : ''}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <div className={styles.emptyState}>No child reviews have been accepted yet.</div>
            )}
          </div>

          <div className={styles.manifestGroup}>
            <div className={styles.manifestGroupHeader}>
              <h4 className={styles.manifestGroupTitle}>Current active sibling</h4>
              <span className={styles.metricPill}>{activeSibling ? 1 : 0}</span>
            </div>
            {activeSibling ? (
              <ul className={styles.list}>
                <li className={styles.listItem}>
                  <div className={styles.listRow}>
                    <strong>
                      {formatReviewChainLabel(parentHierarchicalNumber, activeSibling.index)}{' '}
                      {activeSibling.title}
                    </strong>
                    <span className={styles.metaText}>Active</span>
                  </div>
                  {activeSibling.objective ? (
                    <p className={styles.bodyText}>{activeSibling.objective}</p>
                  ) : null}
                  <p className={styles.metaText}>
                    {activeSibling.materialized_node_id
                      ? `Materialized as ${activeSibling.materialized_node_id}`
                      : 'Materialized sibling is active but node id is not available.'}
                  </p>
                </li>
              </ul>
            ) : (
              <div className={styles.emptyState}>No active sibling is currently in progress.</div>
            )}
          </div>

          <div className={styles.manifestGroup}>
            <div className={styles.manifestGroupHeader}>
              <h4 className={styles.manifestGroupTitle}>Remaining pending siblings</h4>
              <span className={styles.metricPill}>{pendingSiblings.length}</span>
            </div>
            {pendingSiblings.length ? (
              <ul className={styles.list}>
                {pendingSiblings.map((sibling) => (
                  <li key={sibling.index} className={styles.listItem}>
                    <div className={styles.listRow}>
                      <strong>
                        {formatReviewChainLabel(parentHierarchicalNumber, sibling.index)} {sibling.title}
                      </strong>
                      <span className={styles.metaText}>Pending</span>
                    </div>
                    {sibling.objective ? <p className={styles.bodyText}>{sibling.objective}</p> : null}
                    <p className={styles.metaText}>
                      {sibling.index > 1
                        ? `Waiting for ${formatReviewChainLabel(parentHierarchicalNumber, sibling.index - 1)} review.`
                        : 'Waiting to be materialized.'}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <div className={styles.emptyState}>No remaining lazy siblings are queued.</div>
            )}
          </div>
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <p className={styles.sectionEyebrow}>Integration Rollup</p>
            <h3 className={styles.sectionTitle}>Rollup Output</h3>
          </div>
          {canAcceptRollup ? (
            <button
              type="button"
              className={styles.acceptButton}
              onClick={() => void handleAcceptRollup()}
              disabled={isAccepting}
              data-testid="accept-rollup-button"
            >
              {isAccepting ? 'Accepting...' : 'Accept Rollup'}
            </button>
          ) : null}
        </div>
        {rollupSummary ? (
          <div className={styles.summaryCard}>
            <p className={styles.summaryHeading}>{rollupSummary.heading}</p>
            {rollupSummary.summary ? <p className={styles.bodyText}>{rollupSummary.summary}</p> : null}
            {rollupSummary.sha ? <p className={styles.metaText}>SHA: {rollupSummary.sha}</p> : null}
            {rollupSummary.timestamp ? (
              <p className={styles.metaText}>
                {reviewState.rollup.status === 'accepted' ? 'Accepted at' : 'Generated at'}{' '}
                {rollupSummary.timestamp}
              </p>
            ) : null}
          </div>
        ) : reviewState.rollup.status === 'ready' ? (
          <div className={styles.emptyState}>
            Integration analysis is ready, but the draft package has not been produced yet.
          </div>
        ) : (
          <div className={styles.emptyState}>
            Rollup stays pending until every local child review in this package has been accepted.
          </div>
        )}
      </section>
    </div>
  )
}
