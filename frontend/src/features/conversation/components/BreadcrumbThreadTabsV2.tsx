import styles from '../../breadcrumb/BreadcrumbChatView.module.css'
import type { ThreadTab } from '../surfaceRouting'

type BreadcrumbThreadTabsV2Props = {
  threadTab: ThreadTab
  onThreadTabChange: (threadTab: ThreadTab) => void
}

export function BreadcrumbThreadTabsV2({
  threadTab,
  onThreadTabChange,
}: BreadcrumbThreadTabsV2Props) {
  return (
    <div className={styles.threadTabBar} data-testid="breadcrumb-v2-thread-header">
      <nav className={styles.threadTabNav} role="tablist" aria-label="Thread mode">
        <button
          type="button"
          role="tab"
          className={`${styles.threadTab} ${threadTab === 'ask' ? styles.threadTabActive : ''}`}
          data-testid="breadcrumb-thread-tab-ask"
          aria-selected={threadTab === 'ask'}
          onClick={() => onThreadTabChange('ask')}
        >
          Ask
        </button>
        <button
          type="button"
          role="tab"
          className={`${styles.threadTab} ${threadTab === 'execution' ? styles.threadTabActive : ''}`}
          data-testid="breadcrumb-thread-tab-execution"
          aria-selected={threadTab === 'execution'}
          onClick={() => onThreadTabChange('execution')}
        >
          Execution
        </button>
        <button
          type="button"
          role="tab"
          className={`${styles.threadTab} ${threadTab === 'audit' ? styles.threadTabActive : ''}`}
          data-testid="breadcrumb-thread-tab-audit"
          aria-selected={threadTab === 'audit'}
          onClick={() => onThreadTabChange('audit')}
        >
          Review
        </button>
      </nav>
    </div>
  )
}
