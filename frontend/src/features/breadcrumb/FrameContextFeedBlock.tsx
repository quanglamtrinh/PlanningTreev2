import { useEffect, useMemo, useState } from 'react'
import type { ClarifyQuestion, NodeRecord } from '../../api/types'
import { useClarifyStore } from '../../stores/clarify-store'
import { useNodeDocumentStore } from '../../stores/node-document-store'
import { FrameMarkdownViewer } from './FrameMarkdownViewer'
import styles from './FrameContextFeedBlock.module.css'

// ─── Types ─────────────────────────────────────────────────────────

type PanelId = 'frame' | 'clarify' | 'split' | 'spec'

type FrameContextVariant = 'ask' | 'audit'

type Props = {
  projectId: string
  nodeId: string
  nodeRegistry: NodeRecord[]
  /** Ask: current node has Frame+Clarify only; Audit: current node can add Spec when confirmed. */
  variant?: FrameContextVariant
  /** From detail state for the breadcrumb node; only used when variant is audit. */
  specConfirmed?: boolean
}

// ─── Helpers ───────────────────────────────────────────────────────

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

function panelKey(nodeId: string, panelId: PanelId): string {
  return `${nodeId}::${panelId}`
}

function defaultExpanded(panelId: PanelId, isCurrent: boolean): boolean {
  if (isCurrent) {
    if (panelId === 'spec') return false
    return panelId === 'frame'
  }
  return panelId === 'split'
}

function resolveAnswer(q: ClarifyQuestion): string | null {
  if (q.selected_option_id) {
    const opt = q.options.find((o) => o.id === q.selected_option_id)
    return opt?.label ?? null
  }
  if (q.custom_answer.trim()) {
    return q.custom_answer.trim()
  }
  return null
}

// ─── Chevron icon ───────────────────────────────────────────────────

function Chevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`${styles.chevron} ${expanded ? '' : styles.chevronCollapsed}`}
      viewBox="0 0 12 12"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden
    >
      <path
        d="M2 4.5L6 8.5L10 4.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// ─── Read-only clarify Q/A view ─────────────────────────────────────

function ContextClarifyView({ questions }: { questions: ClarifyQuestion[] }) {
  if (questions.length === 0) {
    return <div className={styles.stateEmpty}>No clarify questions.</div>
  }

  return (
    <div className={styles.qaList}>
      {questions.map((q, idx) => {
        const answer = resolveAnswer(q)
        return (
          <div key={q.field_name} className={styles.qaItem}>
            <span className={styles.qaQuestion}>
              {idx + 1}. {q.question}
            </span>
            {answer ? (
              <span className={styles.qaAnswer}>{answer}</span>
            ) : (
              <span className={styles.qaAnswerEmpty}>Not answered</span>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ─── Child node list (split view) ───────────────────────────────────

function ContextSplitView({
  node,
  nodeRegistry,
  currentNodeId,
}: {
  node: NodeRecord
  nodeRegistry: NodeRecord[]
  currentNodeId: string
}) {
  const byId = useMemo(
    () => new Map(nodeRegistry.map((n) => [n.node_id, n])),
    [nodeRegistry],
  )

  const children = useMemo(
    () =>
      node.child_ids
        .map((id) => byId.get(id))
        .filter((n): n is NodeRecord => n !== undefined),
    [node.child_ids, byId],
  )

  if (children.length === 0) {
    return <div className={styles.stateEmpty}>No subtasks.</div>
  }

  return (
    <div className={styles.childList}>
      {children.map((child) => {
        const isCurrent = child.node_id === currentNodeId
        return (
          <div key={child.node_id} className={styles.childItem}>
            {child.hierarchical_number && (
              <span className={styles.childNumber}>{child.hierarchical_number}</span>
            )}
            <span className={`${styles.childTitle} ${isCurrent ? styles.childTitleCurrent : ''}`}>
              {child.title}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ─── Individual panel (Frame / Clarify / Split) ─────────────────────

type PanelProps = {
  label: string
  panelId: PanelId
  nodeId: string
  expanded: boolean
  onToggle: (nodeId: string, panelId: PanelId) => void
  children: React.ReactNode
}

function NodePanel({ label, panelId, nodeId, expanded, onToggle, children }: PanelProps) {
  return (
    <div className={styles.panel}>
      <button
        type="button"
        className={styles.panelToggle}
        aria-expanded={expanded}
        onClick={() => onToggle(nodeId, panelId)}
      >
        <Chevron expanded={expanded} />
        <span className={styles.panelLabel}>{label}</span>
      </button>
      {expanded && <div className={styles.panelBody}>{children}</div>}
    </div>
  )
}

// ─── Main component ─────────────────────────────────────────────────

export function FrameContextFeedBlock({
  projectId,
  nodeId,
  nodeRegistry,
  variant = 'ask',
  specConfirmed = false,
}: Props) {
  const chain = useMemo(
    () => buildAncestorChain(nodeId, nodeRegistry),
    [nodeId, nodeRegistry],
  )

  // Per-panel expand state: key = "${nodeId}::${panelId}"
  const [expandedMap, setExpandedMap] = useState<Record<string, boolean>>({})

  const isPanelExpanded = (nId: string, pId: PanelId, isCurrent: boolean): boolean => {
    const key = panelKey(nId, pId)
    return key in expandedMap ? expandedMap[key] : defaultExpanded(pId, isCurrent)
  }

  const togglePanel = (nId: string, pId: PanelId) => {
    setExpandedMap((prev) => {
      const key = panelKey(nId, pId)
      // Determine current effective value including default
      const isCurrent = nId === nodeId
      const current = key in prev ? prev[key] : defaultExpanded(pId, isCurrent)
      return { ...prev, [key]: !current }
    })
  }

  // Reset expanded state when navigating to a different node
  useEffect(() => {
    setExpandedMap({})
  }, [nodeId])

  // Load frame documents
  const loadDocument = useNodeDocumentStore((s) => s.loadDocument)
  const frameEntries = useNodeDocumentStore((s) => s.entries)

  useEffect(() => {
    for (const node of chain) {
      void loadDocument(projectId, node.node_id, 'frame').catch(() => undefined)
    }
  }, [chain, projectId, loadDocument])

  useEffect(() => {
    if (variant !== 'audit' || !specConfirmed) return
    void loadDocument(projectId, nodeId, 'spec').catch(() => undefined)
  }, [variant, specConfirmed, projectId, nodeId, loadDocument])

  // Load clarify data
  const loadClarify = useClarifyStore((s) => s.loadClarify)
  const clarifyEntries = useClarifyStore((s) => s.entries)

  useEffect(() => {
    for (const node of chain) {
      void loadClarify(projectId, node.node_id).catch(() => undefined)
    }
  }, [chain, projectId, loadClarify])

  return (
    <div className={styles.feedBlock}>
      <div className={styles.eyebrow}>Context</div>

      <div className={styles.nodeList}>
        {chain.map((node) => {
          const isCurrent = node.node_id === nodeId
          const shapingFrozen = node.workflow?.shaping_frozen === true

          const frameEntry = frameEntries[`${projectId}::${node.node_id}::frame`]
          const specEntry = frameEntries[`${projectId}::${node.node_id}::spec`]
          const clarifyEntry = clarifyEntries[`${projectId}::${node.node_id}`]
          const clarifyQuestions = clarifyEntry?.clarify?.questions ?? []

          return (
            <div
              key={node.node_id}
              className={`${styles.nodeCard} ${isCurrent ? styles.nodeCardCurrent : ''}`}
            >
              {/* Always-visible node header */}
              <div className={styles.nodeCardHeader}>
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

              {/* Gate: current node panels only shown when shaping is frozen */}
              {isCurrent && !shapingFrozen ? (
                <div className={styles.shapingGate}>
                  Frame context will appear once clarify is confirmed.
                </div>
              ) : (
                <div className={styles.panelList}>
                  {/* Frame panel */}
                  <NodePanel
                    label="Frame"
                    panelId="frame"
                    nodeId={node.node_id}
                    expanded={isPanelExpanded(node.node_id, 'frame', isCurrent)}
                    onToggle={togglePanel}
                  >
                    {!frameEntry || frameEntry.isLoading ? (
                      <div className={styles.stateLoading}>Loading…</div>
                    ) : frameEntry.error ? (
                      <div className={styles.stateError}>{frameEntry.error}</div>
                    ) : !frameEntry.content.trim() ? (
                      <div className={styles.stateEmpty}>No frame content yet.</div>
                    ) : (
                      <FrameMarkdownViewer content={frameEntry.content} />
                    )}
                  </NodePanel>

                  {/* Clarify panel */}
                  <NodePanel
                    label="Clarify"
                    panelId="clarify"
                    nodeId={node.node_id}
                    expanded={isPanelExpanded(node.node_id, 'clarify', isCurrent)}
                    onToggle={togglePanel}
                  >
                    {!clarifyEntry || clarifyEntry.isLoading ? (
                      <div className={styles.stateLoading}>Loading…</div>
                    ) : clarifyEntry.loadError ? (
                      <div className={styles.stateError}>{clarifyEntry.loadError}</div>
                    ) : (
                      <ContextClarifyView questions={clarifyQuestions} />
                    )}
                  </NodePanel>

                  {/* Split — ancestors only (ask + audit) */}
                  {!isCurrent && (
                    <NodePanel
                      label="Split"
                      panelId="split"
                      nodeId={node.node_id}
                      expanded={isPanelExpanded(node.node_id, 'split', isCurrent)}
                      onToggle={togglePanel}
                    >
                      <ContextSplitView
                        node={node}
                        nodeRegistry={nodeRegistry}
                        currentNodeId={nodeId}
                      />
                    </NodePanel>
                  )}

                  {/* Spec — audit + current only, after spec confirmed */}
                  {isCurrent && variant === 'audit' && specConfirmed ? (
                    <NodePanel
                      label="Spec"
                      panelId="spec"
                      nodeId={node.node_id}
                      expanded={isPanelExpanded(node.node_id, 'spec', isCurrent)}
                      onToggle={togglePanel}
                    >
                      {!specEntry || specEntry.isLoading ? (
                        <div className={styles.stateLoading}>Loading…</div>
                      ) : specEntry.error ? (
                        <div className={styles.stateError}>{specEntry.error}</div>
                      ) : !specEntry.content.trim() ? (
                        <div className={styles.stateEmpty}>No spec content yet.</div>
                      ) : (
                        <FrameMarkdownViewer content={specEntry.content} />
                      )}
                    </NodePanel>
                  ) : null}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div className={styles.contextFooter} />
    </div>
  )
}
