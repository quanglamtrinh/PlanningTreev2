import type {
  ExecutionFollowupQueueActions,
  ExecutionFollowupQueueState,
} from './followupQueueTypes'
import {
  renderExecutionQueuePauseReasonLabel,
  renderQueueStatusLabel,
} from './BreadcrumbThreadPaneV2.design'
import styles from '../../breadcrumb/BreadcrumbChatView.module.css'

type ExecutionFollowupQueuePanelV2Props = {
  executionQueueState: ExecutionFollowupQueueState
  executionQueueActions: Pick<
    ExecutionFollowupQueueActions,
    'removeQueued' | 'reorderQueued' | 'sendQueuedNow' | 'confirmQueued' | 'retryQueued' | 'setOperatorPause'
  >
}

export function ExecutionFollowupQueuePanelV2({
  executionQueueState,
  executionQueueActions,
}: ExecutionFollowupQueuePanelV2Props) {
  const executionQueueEntries = executionQueueState.executionFollowupQueue
  const executionQueueHasSending = executionQueueEntries.some((entry) => entry.status === 'sending')
  const executionQueueControlsDisabled = executionQueueHasSending || executionQueueState.isSending
  const executionQueuePauseLabel = renderExecutionQueuePauseReasonLabel(
    executionQueueState.executionQueuePauseReason,
  )
  const {
    removeQueued,
    reorderQueued,
    sendQueuedNow,
    confirmQueued,
    retryQueued,
    setOperatorPause,
  } = executionQueueActions

  return (
    <section
      className={styles.executionQueuePanel}
      aria-label="Queued execution follow-ups"
      data-testid="execution-followup-queue-panel"
    >
      <div className={styles.executionQueueHeader}>
        <div className={styles.executionQueueTitle}>Queued Follow-ups ({executionQueueEntries.length})</div>
        <div className={styles.executionQueueHeaderControls}>
          <span className={styles.executionQueuePauseReason}>{executionQueuePauseLabel}</span>
          <button
            type="button"
            className={styles.executionQueuePauseToggle}
            onClick={() => setOperatorPause(!executionQueueState.executionQueueOperatorPaused)}
            data-testid="execution-followup-operator-pause-toggle"
          >
            {executionQueueState.executionQueueOperatorPaused ? 'Resume auto-send' : 'Pause auto-send'}
          </button>
        </div>
      </div>

      {executionQueueEntries.length === 0 ? (
        <p className={styles.executionQueueEmpty}>No queued follow-ups.</p>
      ) : (
        <ol className={styles.executionQueueList}>
          {executionQueueEntries.map((entry, index) => (
            <li key={entry.entryId} className={styles.executionQueueItem}>
              <div className={styles.executionQueueItemMetaRow}>
                <span
                  className={`${styles.executionQueueStatusBadge} ${
                    entry.status === 'failed'
                      ? styles.executionQueueStatusFailed
                      : entry.status === 'requires_confirmation'
                        ? styles.executionQueueStatusConfirmation
                        : entry.status === 'sending'
                          ? styles.executionQueueStatusSending
                          : styles.executionQueueStatusQueued
                  }`}
                >
                  {renderQueueStatusLabel(entry.status)}
                </span>
                <span className={styles.executionQueueMetaText}>Attempt {entry.attemptCount + 1}</span>
              </div>
              <p className={styles.executionQueueText}>{entry.text}</p>
              {entry.lastError ? (
                <div className={styles.executionQueueError}>Last error: {entry.lastError}</div>
              ) : null}
              <div className={styles.executionQueueActions}>
                <button
                  type="button"
                  className={styles.executionQueueAction}
                  disabled={executionQueueControlsDisabled || index === 0}
                  onClick={() => reorderQueued(index, index - 1)}
                >
                  Move up
                </button>
                <button
                  type="button"
                  className={styles.executionQueueAction}
                  disabled={executionQueueControlsDisabled || index === executionQueueEntries.length - 1}
                  onClick={() => reorderQueued(index, index + 1)}
                >
                  Move down
                </button>
                <button
                  type="button"
                  className={styles.executionQueueAction}
                  disabled={
                    executionQueueControlsDisabled ||
                    entry.status === 'sending' ||
                    entry.status === 'requires_confirmation'
                  }
                  onClick={() => void sendQueuedNow(entry.entryId)}
                >
                  Send now
                </button>
                {entry.status === 'requires_confirmation' ? (
                  <button
                    type="button"
                    className={`${styles.executionQueueAction} ${styles.executionQueueActionPrimary}`}
                    disabled={executionQueueControlsDisabled}
                    onClick={() => void confirmQueued(entry.entryId)}
                  >
                    Confirm
                  </button>
                ) : null}
                {entry.status === 'failed' ? (
                  <button
                    type="button"
                    className={`${styles.executionQueueAction} ${styles.executionQueueActionPrimary}`}
                    disabled={executionQueueControlsDisabled}
                    onClick={() => void retryQueued(entry.entryId)}
                  >
                    Retry
                  </button>
                ) : null}
                <button
                  type="button"
                  className={styles.executionQueueAction}
                  disabled={executionQueueControlsDisabled || entry.status === 'sending'}
                  onClick={() => removeQueued(entry.entryId)}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}
