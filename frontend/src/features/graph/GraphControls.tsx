import type { NodeRecord } from '../../api/types'
import styles from './GraphControls.module.css'

type Props = {
  node: NodeRecord
  isCreatingNode: boolean
  canFinishTask: boolean
  onCreateChild: () => Promise<void>
  onOpenBreadcrumb: () => Promise<void>
  onFinishTask: () => Promise<void>
}

export function GraphControls({
  node,
  isCreatingNode,
  canFinishTask,
  onCreateChild,
  onOpenBreadcrumb,
  onFinishTask,
}: Props) {
  const createDisabled = node.status === 'done' || node.is_superseded

  return (
    <section className={styles.panel}>
      <div className={styles.header}>
        <p className={styles.kicker}>Actions</p>
        <p className={styles.subtitle}>Use breadcrumb as the execution surface for active leaf work.</p>
      </div>

      <div className={styles.primaryActions}>
        <button
          type="button"
          className={styles.primary}
          disabled={createDisabled || isCreatingNode}
          onClick={() => void onCreateChild()}
        >
          {isCreatingNode ? 'Creating child...' : 'Create Child'}
        </button>
        <button type="button" className={styles.secondary} onClick={() => void onOpenBreadcrumb()}>
          Open Breadcrumb
        </button>
      </div>

      <div className={styles.placeholderGrid}>
        <button type="button" disabled>
          Walking Skeleton
        </button>
        <button type="button" disabled>
          Slice
        </button>
        <button type="button" disabled={!canFinishTask} onClick={() => void onFinishTask()}>
          Finish Task
        </button>
      </div>

      <p className={styles.note}>
        Finish Task seeds breadcrumb chat. Mark Done remains inside the breadcrumb workspace.
      </p>
    </section>
  )
}
