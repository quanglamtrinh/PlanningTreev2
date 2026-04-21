import { useEffect, useMemo, useRef, useState } from 'react'
import { useShallow } from 'zustand/react/shallow'
import type { NodeRecord } from '../../api/types'
import { useNodeDocumentStore } from '../../stores/node-document-store'
import { useProjectStore } from '../../stores/project-store'
import { FrameMarkdownViewer } from './FrameMarkdownViewer'
import styles from './NodeFrameContextPanel.module.css'

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

// ─── Per-node frame section ─────────────────────────────────────────

type FrameSectionProps = {
  projectId: string
  node: NodeRecord
  isCurrent: boolean
  projectRootPath?: string
  sectionRef?: React.RefObject<HTMLDivElement>
}

function NodeFrameSection({ projectId, node, isCurrent, projectRootPath, sectionRef }: FrameSectionProps) {
  const entry = useNodeDocumentStore(
    useShallow((s) => s.entries[`${projectId}::${node.node_id}::frame`]),
  )

  return (
    <div
      className={styles.nodeSection}
      ref={isCurrent ? sectionRef : undefined}
    >
      <div
        className={`${styles.nodeSectionHeader} ${isCurrent ? styles.nodeSectionHeaderCurrent : ''}`}
      >
        {node.hierarchical_number && (
          <span className={`${styles.nodeNumber} ${isCurrent ? styles.nodeNumberCurrent : ''}`}>
            {node.hierarchical_number}
          </span>
        )}
        <span className={`${styles.nodeTitle} ${isCurrent ? styles.nodeTitleCurrent : ''}`}>
          {node.title}
        </span>
        <span className={`${styles.frameTag} ${isCurrent ? styles.frameTagCurrent : ''}`}>
          Frame
        </span>
      </div>

      {!entry || entry.isLoading ? (
        <div className={styles.frameLoading}>Loading…</div>
      ) : entry.error ? (
        <div className={styles.frameError}>{entry.error}</div>
      ) : !entry.content.trim() ? (
        <div className={styles.frameEmpty}>No frame content yet.</div>
      ) : (
        <div className={styles.frameContent}>
          <FrameMarkdownViewer content={entry.content} projectRootPath={projectRootPath} />
        </div>
      )}
    </div>
  )
}

// ─── Panel ─────────────────────────────────────────────────────────

export function NodeFrameContextPanel({ projectId, nodeId, nodeRegistry }: Props) {
  const [collapsed, setCollapsed] = useState(false)
  const currentSectionRef = useRef<HTMLDivElement>(null)
  const scrollBodyRef = useRef<HTMLDivElement>(null)
  const projectRootPath = useProjectStore((state) =>
    state.snapshot?.project.id === projectId
      ? state.snapshot.project.project_path
      : undefined,
  )

  const chain = useMemo(
    () => buildAncestorChain(nodeId, nodeRegistry),
    [nodeId, nodeRegistry],
  )

  const loadDocument = useNodeDocumentStore((s) => s.loadDocument)

  // Load frame for each node in the chain
  useEffect(() => {
    for (const node of chain) {
      void loadDocument(projectId, node.node_id, 'frame').catch(() => undefined)
    }
  }, [chain, projectId, loadDocument])

  // Auto-scroll to current node section once its content loads
  const currentEntry = useNodeDocumentStore(
    (s) => s.entries[`${projectId}::${nodeId}::frame`],
  )
  const hasScrolled = useRef(false)

  useEffect(() => {
    if (hasScrolled.current) return
    if (!currentEntry?.hasLoaded) return
    if (collapsed) return
    // Small delay to let the DOM render the content before scrolling
    const id = globalThis.setTimeout(() => {
      currentSectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      hasScrolled.current = true
    }, 80)
    return () => globalThis.clearTimeout(id)
  }, [currentEntry?.hasLoaded, collapsed])

  // Reset scroll tracking when node changes
  useEffect(() => {
    hasScrolled.current = false
  }, [nodeId])

  const ancestorCount = chain.length > 1 ? chain.length - 1 : 0

  return (
    <div className={styles.panel}>
      {/* Panel header */}
      <div
        className={styles.panelHeader}
        onClick={() => setCollapsed((c) => !c)}
        role="button"
        aria-expanded={!collapsed}
        aria-label={collapsed ? 'Expand frame context' : 'Collapse frame context'}
      >
        <button
          type="button"
          className={styles.toggleBtn}
          tabIndex={-1}
          aria-hidden
        >
          <svg
            className={`${styles.toggleIcon} ${collapsed ? styles.toggleIconCollapsed : ''}`}
            viewBox="0 0 12 12"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <path
              d="M2 4.5L6 8.5L10 4.5"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>

        <span className={styles.panelLabel}>Frame Context</span>

        {ancestorCount > 0 && (
          <span className={styles.ancestorChip}>
            {ancestorCount} parent{ancestorCount > 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Scrollable content */}
      {!collapsed && (
        <div className={styles.scrollBody} ref={scrollBodyRef}>
          {chain.map((node) => (
            <NodeFrameSection
              key={node.node_id}
              projectId={projectId}
              node={node}
              isCurrent={node.node_id === nodeId}
              projectRootPath={projectRootPath}
              sectionRef={currentSectionRef}
            />
          ))}
        </div>
      )}
    </div>
  )
}
