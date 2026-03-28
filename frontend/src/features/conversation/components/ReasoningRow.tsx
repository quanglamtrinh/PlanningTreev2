import type { ReasoningItem } from '../../../api/types'
import { ConversationMarkdown } from './ConversationMarkdown'
import styles from './ConversationFeed.module.css'

export function ReasoningRow({ item }: { item: ReasoningItem }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-reasoning">
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>Reasoning</div>
          </div>
          <div className={`${styles.statusPill} ${styles.statusInProgress}`}>{item.status}</div>
        </div>
        <ConversationMarkdown content={item.summaryText} />
        {item.detailText ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Details</div>
            <ConversationMarkdown content={item.detailText} />
          </div>
        ) : null}
      </div>
    </article>
  )
}
