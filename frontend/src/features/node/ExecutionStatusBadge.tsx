import type { ExecutionStatus } from '../../api/types'
import styles from './ExecutionStatusBadge.module.css'

const LABELS: Record<Exclude<ExecutionStatus, 'idle'>, string> = {
  executing: 'Executing',
  completed: 'Execution Complete',
  failed: 'Failed',
  review_pending: 'In Review',
  review_accepted: 'Accepted',
}

type Props = {
  status?: ExecutionStatus | null
  className?: string
}

export function ExecutionStatusBadge({ status, className: extraClassName }: Props) {
  if (!status || status === 'idle') {
    return null
  }

  const className = [styles.badge, styles[status], extraClassName].filter(Boolean).join(' ')
  return <span className={className}>{LABELS[status]}</span>
}
