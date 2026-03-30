import type { ErrorItem } from '../../../api/types'
import styles from './ConversationFeed.module.css'

export function ErrorRow({ item }: { item: ErrorItem }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-error">
      <div className={`${styles.card} ${styles.errorCard}`}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>Error</div>
            <h3 className={styles.cardTitle}>{item.title}</h3>
          </div>
          <div className={`${styles.statusPill} ${styles.statusFailed}`}>{item.code}</div>
        </div>
        <div className={styles.subtleText}>{item.message}</div>
      </div>
    </article>
  )
}
