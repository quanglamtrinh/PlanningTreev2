import type { ThreadTab } from '../surfaceRouting'
import { BREADCRUMB_THREAD_TAB_DESIGN } from './BreadcrumbThreadPaneV2.design'
import styles from '../../session_v2/shell/SessionConsoleV2.module.css'

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
        {BREADCRUMB_THREAD_TAB_DESIGN.map((tab) => (
          <button
            key={tab.value}
            type="button"
            role="tab"
            className={`${styles.threadTab} ${threadTab === tab.value ? styles.threadTabActive : ''}`}
            data-testid={tab.testId}
            aria-selected={threadTab === tab.value}
            onClick={() => onThreadTabChange(tab.value)}
          >
            {tab.label}
          </button>
        ))}
      </nav>
    </div>
  )
}
