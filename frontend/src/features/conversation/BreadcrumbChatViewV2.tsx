import type { NodeRecord } from '../../api/types'
import styles from '../breadcrumb/BreadcrumbChatView.module.css'
import { NodeDetailCard } from '../node/NodeDetailCard'
import { BreadcrumbThreadPaneV2, type BreadcrumbThreadPaneV2Props } from './components/BreadcrumbThreadPaneV2'

export type BreadcrumbDetailPaneProps = {
  projectId: string | null
  node: NodeRecord | null
  state: 'ready' | 'loading' | 'unavailable'
  message: string | null
}

export type BreadcrumbChatViewV2Props = {
  threadPaneProps: BreadcrumbThreadPaneV2Props
  detailPaneProps: BreadcrumbDetailPaneProps
}

export function BreadcrumbChatViewV2({
  threadPaneProps,
  detailPaneProps,
}: BreadcrumbChatViewV2Props) {
  return (
    <div className={styles.root}>
      <BreadcrumbThreadPaneV2 {...threadPaneProps} />

      <aside className={styles.detailPane} data-testid="breadcrumb-detail-pane">
        <div className={styles.detailRail}>
          <NodeDetailCard
            projectId={detailPaneProps.projectId}
            node={detailPaneProps.node}
            variant="breadcrumb"
            showClose={false}
            state={detailPaneProps.state}
            message={detailPaneProps.message}
          />
        </div>
      </aside>
    </div>
  )
}
