import { useEffect, useMemo } from 'react'
import type { NodeRecord } from '../../api/types'
import { useNodeDocumentStore } from '../../stores/node-document-store'
import { FrameMarkdownViewer } from './FrameMarkdownViewer'
import styles from './FrameContextFeedBlock.module.css'

type Props = {
  projectId: string
  nodeId: string
  nodeRegistry: NodeRecord[]
}

function buildAncestorChain(nodeId: string, registry: NodeRecord[]): NodeRecord[] {
  const byId = new Map(registry.map((n) => [n.node_id, n]))
  const chain: NodeRecord[] = []
  let cursor: string | null = nodeId
  while (cursor) {
    const node = byId.get(cursor)
    if (!node) break
    chain.unshift(node)
    cursor = node.parent_id
  }
  return chain
}

export function FrameContextFeedBlock({ projectId, nodeId, nodeRegistry }: Props) {
  const chain = useMemo(
    () => buildAncestorChain(nodeId, nodeRegistry),
    [nodeId, nodeRegistry],
  )

  const loadDocument = useNodeDocumentStore((s) => s.loadDocument)
  const entries = useNodeDocumentStore((s) => s.entries)

  useEffect(() => {
    for (const node of chain) {
      void loadDocument(projectId, node.node_id, 'frame').catch(() => undefined)
    }
  }, [chain, projectId, loadDocument])

  return (
    <div className={styles.feedBlock}>
      <div className={styles.eyebrow}>Frame Context</div>

      {chain.map((node, idx) => {
        const isCurrent = node.node_id === nodeId
        const entry = entries[`${projectId}::${node.node_id}::frame`]

        return (
          <div key={node.node_id} className={styles.nodeSection}>
            {idx > 0 && <div className={styles.sectionDivider} />}

            <div className={styles.nodeHeader}>
              {node.hierarchical_number && (
                <span className={`${styles.nodeNumber} ${isCurrent ? styles.nodeNumberCurrent : ''}`}>
                  {node.hierarchical_number}
                </span>
              )}
              <span className={`${styles.nodeTitle} ${isCurrent ? styles.nodeTitleCurrent : ''}`}>
                {node.title}
              </span>
              {isCurrent && <span className={styles.currentBadge}>current</span>}
            </div>

            {!entry || entry.isLoading ? (
              <div className={styles.stateLoading}>Loading frame…</div>
            ) : entry.error ? (
              <div className={styles.stateError}>{entry.error}</div>
            ) : !entry.content.trim() ? (
              <div className={styles.stateEmpty}>No frame content yet.</div>
            ) : (
              <div className={styles.frameContent}>
                <FrameMarkdownViewer content={entry.content} />
              </div>
            )}
          </div>
        )
      })}

      <div className={styles.contextFooter} />
    </div>
  )
}
