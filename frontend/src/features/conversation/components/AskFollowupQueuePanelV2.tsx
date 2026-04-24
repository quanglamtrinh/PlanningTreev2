import type {
  ThreadAskFollowupQueueActions,
  ThreadAskFollowupQueueState,
} from '../state/threadByIdStoreV3'
import {
  renderAskConfirmationReasonLabel,
  renderAskQueuePauseReasonLabel,
  renderQueueStatusLabel,
} from './BreadcrumbThreadPaneV2.design'
import styles from '../../breadcrumb/BreadcrumbChatView.module.css'

type AskFollowupQueuePanelV2Props = {
  askQueueState: ThreadAskFollowupQueueState
  askQueueActions: Pick<
    ThreadAskFollowupQueueActions,
    'removeQueued' | 'reorderAskQueued' | 'sendAskQueuedNow' | 'confirmQueued' | 'retryAskQueued'
  >
}

export function AskFollowupQueuePanelV2({
  askQueueState,
  askQueueActions,
}: AskFollowupQueuePanelV2Props) {
  const askQueueEntries = askQueueState.askFollowupQueue
  const askQueueHasSending = askQueueEntries.some((entry) => entry.status === 'sending')
  const askQueueControlsDisabled = askQueueHasSending || askQueueState.isSending
  const askQueuePauseLabel = renderAskQueuePauseReasonLabel(askQueueState.askQueuePauseReason)
  const {
    removeQueued,
    reorderAskQueued,
    sendAskQueuedNow,
    confirmQueued,
    retryAskQueued,
  } = askQueueActions

  return (
    <section
      className={styles.askQueuePanel}
      aria-label="Queued ask follow-ups"
      data-testid="ask-followup-queue-panel"
    >
      <div className={styles.askQueueHeader}>
        <div className={styles.askQueueTitle}>Queued Ask Follow-ups ({askQueueEntries.length})</div>
        <div className={styles.askQueueHeaderControls}>
          <span className={styles.askQueuePauseReason}>{askQueuePauseLabel}</span>
        </div>
      </div>

      {askQueueEntries.length === 0 ? (
        <p className={styles.askQueueEmpty}>No queued ask follow-ups.</p>
      ) : (
        <ol className={styles.askQueueList}>
          {askQueueEntries.map((entry, index) => (
            <li key={entry.entryId} className={styles.askQueueItem}>
              <div className={styles.askQueueItemMetaRow}>
                <span
                  className={`${styles.askQueueStatusBadge} ${
                    entry.status === 'failed'
                      ? styles.askQueueStatusFailed
                      : entry.status === 'requires_confirmation'
                        ? styles.askQueueStatusConfirmation
                        : entry.status === 'sending'
                          ? styles.askQueueStatusSending
                          : styles.askQueueStatusQueued
                  }`}
                >
                  {renderQueueStatusLabel(entry.status)}
                </span>
                <span className={styles.askQueueMetaText}>Attempt {entry.attemptCount + 1}</span>
              </div>
              <p className={styles.askQueueText}>{entry.text}</p>
              {entry.status === 'requires_confirmation' ? (
                <div className={styles.askQueueReason}>
                  {renderAskConfirmationReasonLabel(entry.confirmationReason)}
                </div>
              ) : null}
              {entry.lastError ? (
                <div className={styles.askQueueError}>Last error: {entry.lastError}</div>
              ) : null}
              <div className={styles.askQueueActions}>
                <button
                  type="button"
                  className={styles.askQueueAction}
                  disabled={askQueueControlsDisabled || index === 0}
                  onClick={() => reorderAskQueued(index, index - 1)}
                >
                  Move up
                </button>
                <button
                  type="button"
                  className={styles.askQueueAction}
                  disabled={askQueueControlsDisabled || index === askQueueEntries.length - 1}
                  onClick={() => reorderAskQueued(index, index + 1)}
                >
                  Move down
                </button>
                <button
                  type="button"
                  className={styles.askQueueAction}
                  disabled={askQueueControlsDisabled || index !== 0 || entry.status !== 'queued'}
                  onClick={() => void sendAskQueuedNow(entry.entryId)}
                >
                  Send now
                </button>
                {entry.status === 'requires_confirmation' ? (
                  <button
                    type="button"
                    className={`${styles.askQueueAction} ${styles.askQueueActionPrimary}`}
                    disabled={askQueueControlsDisabled}
                    onClick={() => void confirmQueued(entry.entryId)}
                  >
                    Confirm
                  </button>
                ) : null}
                {entry.status === 'failed' ? (
                  <button
                    type="button"
                    className={`${styles.askQueueAction} ${styles.askQueueActionPrimary}`}
                    disabled={askQueueControlsDisabled}
                    onClick={() => void retryAskQueued(entry.entryId)}
                  >
                    Retry
                  </button>
                ) : null}
                <button
                  type="button"
                  className={styles.askQueueAction}
                  disabled={askQueueControlsDisabled || entry.status === 'sending'}
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
