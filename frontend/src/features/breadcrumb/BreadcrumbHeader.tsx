import type { NodeRecord } from '../../api/types'
import styles from './BreadcrumbHeader.module.css'

type Props = {
  nodes: NodeRecord[]
  nodeId: string
  onBack: () => void
}

function buildCrumbs(nodes: NodeRecord[], nodeId: string): NodeRecord[] {
  const byId = new Map(nodes.map((node) => [node.node_id, node]))
  const chain: NodeRecord[] = []
  const visited = new Set<string>()
  let current = byId.get(nodeId)
  while (current && !visited.has(current.node_id)) {
    visited.add(current.node_id)
    chain.unshift(current)
    current = current.parent_id ? byId.get(current.parent_id) : undefined
  }
  return chain
}

export function BreadcrumbHeader({ nodes, nodeId, onBack }: Props) {
  const crumbs = buildCrumbs(nodes, nodeId)

  return (
    <div className={styles.header}>
      <button type="button" className={styles.back} onClick={onBack}>
        Back to Graph
      </button>
      <nav className={styles.trail} aria-label="Node ancestry">
        {crumbs.map((crumb, index) => (
          <span key={crumb.node_id} className={styles.segmentWrap}>
            {index > 0 ? <span className={styles.sep}>/</span> : null}
            <span
              className={`${styles.segment} ${crumb.node_id === nodeId ? styles.active : ''}`}
              title={`${crumb.hierarchical_number} - ${crumb.title}`}
              aria-current={crumb.node_id === nodeId ? 'page' : undefined}
            >
              {crumb.hierarchical_number} - {crumb.title}
            </span>
          </span>
        ))}
      </nav>
    </div>
  )
}
