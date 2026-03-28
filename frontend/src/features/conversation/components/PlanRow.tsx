import type { PlanItem } from '../../../api/types'
import { ConversationMarkdown } from './ConversationMarkdown'
import styles from './ConversationFeed.module.css'

export function PlanRow({ item }: { item: PlanItem }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-plan">
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>Plan</div>
            {item.title ? <h3 className={styles.cardTitle}>{item.title}</h3> : null}
          </div>
          <div className={`${styles.statusPill} ${styles.statusInProgress}`}>{item.status}</div>
        </div>
        <ConversationMarkdown content={item.text} />
        {item.steps.length ? (
          <div className={styles.stepList}>
            {item.steps.map((step) => (
              <div key={step.id} className={styles.stepItem}>
                <span className={styles.subtleText}>{step.text}</span>
                <span className={styles.statusPill}>{step.status}</span>
              </div>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  )
}
