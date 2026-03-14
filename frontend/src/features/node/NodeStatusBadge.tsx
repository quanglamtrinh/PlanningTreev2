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
}

export function NodeStatusBadge({ status }: Props) {
  const className = `${styles.badge} ${styles[status]}`
  return <span className={className}>{LABELS[status]}</span>
}
