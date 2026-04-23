import styles from '../../breadcrumb/BreadcrumbChatView.module.css'
import type {
  ExecutionFollowupQueueStatus,
  ThreadExecutionFollowupQueueActions,
  ThreadExecutionFollowupQueueState,
} from '../state/threadByIdStoreV3'

type ExecutionFollowupQueuePanelV2Props = {
  executionQueueState: ThreadExecutionFollowupQueueState
  executionQueueActions: Pick<
    ThreadExecutionFollowupQueueActions,
    'removeQueued' | 'reorderQueued' | 'sendQueuedNow' | 'confirmQueued' | 'retryQueued' | 'setOperatorPause'
  >
}

function renderQueueStatusLabel(status: ExecutionFollowupQueueStatus): string {
  if (status === 'queued') {
    return 'Queued'
  }
  if (status === 'requires_confirmation') {
    return 'Needs confirmation'
  }
  if (status === 'sending') {
    return 'Sending'
  }
  return 'Failed'
}

function renderQueuePauseReasonLabel(reason: ThreadExecutionFollowupQueueState['executionQueuePauseReason']): string {
  if (reason === 'none') {
    return 'Auto-send ready'
  }
  if (reason === 'runtime_waiting_input') {
    return 'Paused: waiting for required input'
  }
  if (reason === 'plan_ready_gate') {
    return 'Paused: plan-ready gate'
  }
  if (reason === 'operator_pause') {
    return 'Paused by operator'
  }
  return 'Paused: workflow blocked'
}

export function ExecutionFollowupQueuePanelV2({
  executionQueueState,
  executionQueueActions,
}: ExecutionFollowupQueuePanelV2Props) {
  const executionQueueEntries = executionQueueState.executionFollowupQueue
  const executionQueueHasSending = executionQueueEntries.some((entry) => entry.status === 'sending')
  const executionQueueControlsDisabled = executionQueueHasSending || executionQueueState.isSending
  const executionQueuePauseLabel = renderQueuePauseReasonLabel(executionQueueState.executionQueuePauseReason)
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
