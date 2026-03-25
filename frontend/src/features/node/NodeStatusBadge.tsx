import type { NodeStatus } from '../../api/types'
import styles from './NodeStatusBadge.module.css'

const LABELS: Record<NodeStatus, string> = {
  locked: 'Locked',
  draft: 'Draft',
  ready: 'Ready',
  in_progress: 'In Progress',
  done: 'Done',
}

type Props = {
  status: NodeStatus
  /** Merged after base badge styles (e.g. graph card density). */
  className?: string
}

export function NodeStatusBadge({ status, className: extraClassName }: Props) {
  const className = [styles.badge, styles[status], extraClassName].filter(Boolean).join(' ')
  return <span className={className}>{LABELS[status]}</span>
}
