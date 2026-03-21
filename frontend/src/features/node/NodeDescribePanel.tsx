import type { NodeRecord } from '../../api/types'
import styles from './NodeDetailCard.module.css'

type Props = {
  node: NodeRecord
}

export function NodeDescribePanel({ node }: Props) {
  return (
    <div className={styles.describePanel}>
      <div className={styles.contentPanel}>
        <p className={styles.eyebrow}>
          {node.hierarchical_number ? `${node.hierarchical_number} - Node` : 'Node'}
        </p>
        <h3 className={styles.title}>{node.title}</h3>
        <p className={styles.body}>{node.description.trim() || 'No description yet.'}</p>
        <p className={styles.body}>
          Status: <strong>{node.status}</strong> . Children: {node.child_ids.length}
        </p>
      </div>
    </div>
  )
}
