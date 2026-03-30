import type { StatusItem } from '../../../api/types'
import styles from './ConversationFeed.module.css'

export function StatusRow({ item }: { item: StatusItem }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-status">
      <div className={`${styles.card} ${styles.statusCard}`}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>Status</div>
            <h3 className={styles.cardTitle}>{item.label}</h3>
          </div>
          <div className={styles.statusPill}>{item.code}</div>
        </div>
        {item.detail ? <div className={styles.subtleText}>{item.detail}</div> : null}
      </div>
    </article>
  )
}
