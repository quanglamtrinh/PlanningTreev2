import styles from './StatusPill.module.css'

interface StatusPillProps {
  label: string
}

export function StatusPill({ label }: StatusPillProps) {
  return (
    <div className={styles.root}>
      <span className={styles.dot} />
      <span className={styles.label}>{label}</span>
    </div>
  )
}
