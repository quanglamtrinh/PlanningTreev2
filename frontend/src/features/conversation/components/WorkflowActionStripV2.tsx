import type { ReactNode } from 'react'
import styles from '../../session_v2/shell/SessionConsoleV2.module.css'

type WorkflowActionStripV2Props = {
  actions: ReactNode | null
}

export function WorkflowActionStripV2({ actions }: WorkflowActionStripV2Props) {
  if (!actions) {
    return null
  }
  return (
    <div className={styles.workflowActionStrip} data-testid="workflow-action-strip">
      <div className={styles.workflowActionStripInner}>{actions}</div>
    </div>
  )
}
