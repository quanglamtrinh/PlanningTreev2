import { AgentSpinner } from '../../../components/AgentSpinner'
import type { ProcessingState } from '../../../api/types'
import styles from './ConversationFeed.module.css'

function formatDuration(durationMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

export function WorkingIndicator({
  processingState,
  activeTurnId,
  lastCompletedAt,
  lastDurationMs,
}: {
  processingState: ProcessingState
  activeTurnId: string | null
  lastCompletedAt?: number | null
  lastDurationMs?: number | null
}) {
  if (processingState === 'running' && activeTurnId) {
    return (
      <div className={styles.row} data-testid="conversation-working-indicator">
        <div className={styles.workingIndicator}>
          <AgentSpinner />
        </div>
      </div>
    )
  }

  if (processingState === 'waiting_user_input') {
    return (
      <div className={styles.row} data-testid="conversation-working-indicator">
        <div className={styles.workingIndicator}>
          <span className={styles.workingText}>Waiting for user input.</span>
        </div>
      </div>
    )
  }

  if (lastCompletedAt != null && lastDurationMs != null && Date.now() - lastCompletedAt < 4000) {
    return (
      <div className={styles.row} data-testid="conversation-working-indicator">
        <div className={styles.workingIndicator}>
          <span className={styles.workingText}>Completed.</span>
          <span className={styles.workingMeta}>{formatDuration(lastDurationMs)}</span>
        </div>
      </div>
    )
  }

  return null
}
