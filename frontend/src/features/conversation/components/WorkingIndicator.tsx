import { AgentSpinner } from '../../../components/AgentSpinner'
import type { ProcessingState } from '../../../api/types'
import styles from './ConversationFeed.module.css'

export function WorkingIndicator({
  processingState,
  activeTurnId,
}: {
  processingState: ProcessingState
  activeTurnId: string | null
}) {
  if (processingState === 'running' && activeTurnId) {
    return (
      <div className={styles.row}>
        <div className={styles.workingIndicator}>
          <AgentSpinner />
          <span className={styles.workingText}>Working on the current turn.</span>
        </div>
      </div>
    )
  }

  if (processingState === 'waiting_user_input') {
    return (
      <div className={styles.row}>
        <div className={styles.workingIndicator}>
          <span className={styles.workingText}>Waiting for user input.</span>
        </div>
      </div>
    )
  }

  return null
}
