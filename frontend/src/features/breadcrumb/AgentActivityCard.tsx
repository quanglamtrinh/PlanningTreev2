import styles from './AgentActivityCard.module.css'

type Tone = 'neutral' | 'positive' | 'negative'

type Props = {
  title?: string
  status: string
  message: string
  tone?: Tone
  actionLabel?: string
  onAction?: () => void
}

export function AgentActivityCard({
  title = 'Agent Activity',
  status,
  message,
  tone = 'neutral',
  actionLabel,
  onAction,
}: Props) {
  return (
    <section className={`${styles.card} ${styles[tone]}`} data-testid="agent-activity-card">
      <div className={styles.copyBlock}>
        <p className={styles.title}>{title}</p>
        <h4 className={styles.status}>{status}</h4>
        <p className={styles.message}>{message}</p>
      </div>
      {actionLabel && onAction ? (
        <button type="button" className={styles.actionButton} onClick={onAction}>
          {actionLabel}
        </button>
      ) : null}
    </section>
  )
}
