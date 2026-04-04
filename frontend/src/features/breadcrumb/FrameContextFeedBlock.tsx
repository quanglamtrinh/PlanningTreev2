import { useEffect, useMemo, useState } from 'react'
import type { ClarifyQuestion, NodeRecord } from '../../api/types'
import {
  askShellNodeActionStateKey,
  type AskShellNodeActionState,
  type ShapingArtifact,
  useAskShellActionStore,
} from '../../stores/ask-shell-action-store'
import { useClarifyStore } from '../../stores/clarify-store'
import { useNodeDocumentStore } from '../../stores/node-document-store'
import { FrameMarkdownViewer } from './FrameMarkdownViewer'
import styles from './FrameContextFeedBlock.module.css'

type PanelId = 'frame' | 'clarify' | 'split' | 'spec'
type FrameContextVariant = 'ask' | 'audit'

type Props = {
  projectId: string
  nodeId: string
  nodeRegistry: NodeRecord[]
  variant?: FrameContextVariant
  specConfirmed?: boolean
}

type ActionChipTone = 'running' | 'success' | 'error'

type ActionChip = {
  artifact: ShapingArtifact
  text: string
  tone: ActionChipTone
}

type PanelProps = {
  label: string
  panelId: PanelId
  nodeId: string
  expanded: boolean
  onToggle: (nodeId: string, panelId: PanelId) => void
  children: React.ReactNode
}

function buildAncestorChain(nodeId: string, registry: NodeRecord[]): NodeRecord[] {
  const byId = new Map(registry.map((node) => [node.node_id, node]))
  const chain: NodeRecord[] = []
  let cursor: string | null = nodeId
  while (cursor) {
    const node = byId.get(cursor)
    if (!node) {
      break
    }
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
    return panelId === 'frame'
  }
  return panelId === 'split'
}

function resolveAnswer(question: ClarifyQuestion): string | null {
  if (question.selected_option_id) {
    const selected = question.options.find((option) => option.id === question.selected_option_id)
    return selected?.label ?? null
  }
  const custom = question.custom_answer.trim()
  return custom || null
}

function summarizeArtifactAction(
  actionState: AskShellNodeActionState,
  artifact: ShapingArtifact,
): ActionChip | null {
  const artifactState = actionState[artifact]
  const confirmState = artifactState.confirm
  const generateState = artifactState.generate

  if (confirmState.status === 'running') {
    return { artifact, text: 'Confirming', tone: 'running' }
  }
  if (generateState.status === 'running') {
    return { artifact, text: 'Generating', tone: 'running' }
  }
  if (confirmState.status === 'failed') {
    return { artifact, text: 'Confirm failed', tone: 'error' }
  }
  if (generateState.status === 'failed') {
    return { artifact, text: 'Generate failed', tone: 'error' }
  }
  if (confirmState.status === 'succeeded') {
    return { artifact, text: 'Confirmed', tone: 'success' }
  }
  if (generateState.status === 'succeeded') {
    return { artifact, text: 'Generated', tone: 'success' }
  }
  return null
}

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

function ContextClarifyView({ questions }: { questions: ClarifyQuestion[] }) {
  if (questions.length === 0) {
    return <div className={styles.stateEmpty}>No clarify questions.</div>
  }

  return (
    <div className={styles.qaList}>
      {questions.map((question, index) => {
        const answer = resolveAnswer(question)
        return (
          <div key={question.field_name} className={styles.qaItem}>
            <span className={styles.qaQuestion}>
              {index + 1}. {question.question}
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

function ContextSplitView({
  node,
  nodeRegistry,
  currentNodeId,
}: {
  node: NodeRecord
  nodeRegistry: NodeRecord[]
  currentNodeId: string
}) {
  const byId = useMemo(() => new Map(nodeRegistry.map((item) => [item.node_id, item])), [nodeRegistry])
  const children = useMemo(
    () => node.child_ids.map((id) => byId.get(id)).filter((item): item is NodeRecord => item !== undefined),
    [byId, node.child_ids],
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
            {child.hierarchical_number ? (
              <span className={styles.childNumber}>{child.hierarchical_number}</span>
            ) : null}
            <span className={`${styles.childTitle} ${isCurrent ? styles.childTitleCurrent : ''}`}>
              {child.title}
            </span>
          </div>
        )
      })}
    </div>
  )
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
      {expanded ? <div className={styles.panelBody}>{children}</div> : null}
    </div>
  )
}

export function FrameContextFeedBlock({
  projectId,
  nodeId,
  nodeRegistry,
  variant = 'ask',
  specConfirmed = false,
}: Props) {
  const chain = useMemo(() => buildAncestorChain(nodeId, nodeRegistry), [nodeId, nodeRegistry])
  const actionState = useAskShellActionStore(
    (state) => state.entries[askShellNodeActionStateKey(projectId, nodeId)],
  )
  const currentNodeActionChips = useMemo(() => {
    if (!actionState) {
      return []
    }
    return (['frame', 'clarify', 'spec'] as ShapingArtifact[])
      .map((artifact) => summarizeArtifactAction(actionState, artifact))
      .filter((chip): chip is ActionChip => chip !== null)
  }, [actionState])

  const [expandedMap, setExpandedMap] = useState<Record<string, boolean>>({})

  const isPanelExpanded = (nodePanelId: string, panelId: PanelId, isCurrent: boolean): boolean => {
    const key = panelKey(nodePanelId, panelId)
    return key in expandedMap ? expandedMap[key] : defaultExpanded(panelId, isCurrent)
  }

  const togglePanel = (nodePanelId: string, panelId: PanelId) => {
    setExpandedMap((prev) => {
      const key = panelKey(nodePanelId, panelId)
      const current = key in prev ? prev[key] : defaultExpanded(panelId, nodePanelId === nodeId)
      return { ...prev, [key]: !current }
    })
  }

  useEffect(() => {
    setExpandedMap({})
  }, [nodeId])

  const loadDocument = useNodeDocumentStore((state) => state.loadDocument)
  const frameEntries = useNodeDocumentStore((state) => state.entries)

  useEffect(() => {
    for (const node of chain) {
      void loadDocument(projectId, node.node_id, 'frame').catch(() => undefined)
    }
  }, [chain, loadDocument, projectId])

  useEffect(() => {
    if (variant !== 'audit' || !specConfirmed) {
      return
    }
    void loadDocument(projectId, nodeId, 'spec').catch(() => undefined)
  }, [loadDocument, nodeId, projectId, specConfirmed, variant])

  const loadClarify = useClarifyStore((state) => state.loadClarify)
  const clarifyEntries = useClarifyStore((state) => state.entries)

  useEffect(() => {
    for (const node of chain) {
      void loadClarify(projectId, node.node_id).catch(() => undefined)
    }
  }, [chain, loadClarify, projectId])

  return (
    <div className={styles.feedBlock}>
      <div className={styles.eyebrow}>Context</div>

      <div className={styles.nodeList}>
        {chain.map((node) => {
          const isCurrent = node.node_id === nodeId
          const frameEntry = frameEntries[`${projectId}::${node.node_id}::frame`]
          const specEntry = frameEntries[`${projectId}::${node.node_id}::spec`]
          const clarifyEntry = clarifyEntries[`${projectId}::${node.node_id}`]
          const clarifyQuestions = clarifyEntry?.clarify?.questions ?? []

          return (
            <div key={node.node_id} className={`${styles.nodeCard} ${isCurrent ? styles.nodeCardCurrent : ''}`}>
              <div className={styles.nodeCardHeader}>
                {node.hierarchical_number ? (
                  <span className={`${styles.nodeNumber} ${isCurrent ? styles.nodeNumberCurrent : ''}`}>
                    {node.hierarchical_number}
                  </span>
                ) : null}
                <span className={`${styles.nodeTitle} ${isCurrent ? styles.nodeTitleCurrent : ''}`}>
                  {node.title}
                </span>
                {isCurrent ? <span className={styles.currentBadge}>current</span> : null}
              </div>

              {isCurrent && currentNodeActionChips.length > 0 ? (
                <div className={styles.actionStatusRow} data-testid="frame-context-action-status-row">
                  {currentNodeActionChips.map((chip) => (
                    <span
                      key={chip.artifact}
                      className={`${styles.actionStatusChip} ${
                        chip.tone === 'running'
                          ? styles.actionStatusChipRunning
                          : chip.tone === 'success'
                            ? styles.actionStatusChipSuccess
                            : styles.actionStatusChipError
                      }`}
                      data-testid={`frame-context-action-${chip.artifact}`}
                    >
                      <span className={styles.actionStatusArtifact}>{chip.artifact}</span>
                      <span>{chip.text}</span>
                    </span>
                  ))}
                </div>
              ) : null}

              <div className={styles.panelList}>
                <NodePanel
                  label="Frame"
                  panelId="frame"
                  nodeId={node.node_id}
                  expanded={isPanelExpanded(node.node_id, 'frame', isCurrent)}
                  onToggle={togglePanel}
                >
                  {!frameEntry || frameEntry.isLoading ? (
                    <div className={styles.stateLoading}>Loading...</div>
                  ) : frameEntry.error ? (
                    <div className={styles.stateError}>{frameEntry.error}</div>
                  ) : !frameEntry.content.trim() ? (
                    <div className={styles.stateEmpty}>No frame content yet.</div>
                  ) : (
                    <FrameMarkdownViewer content={frameEntry.content} shellStyle />
                  )}
                </NodePanel>

                <NodePanel
                  label="Clarify"
                  panelId="clarify"
                  nodeId={node.node_id}
                  expanded={isPanelExpanded(node.node_id, 'clarify', isCurrent)}
                  onToggle={togglePanel}
                >
                  {!clarifyEntry || clarifyEntry.isLoading ? (
                    <div className={styles.stateLoading}>Loading...</div>
                  ) : clarifyEntry.loadError ? (
                    <div className={styles.stateError}>{clarifyEntry.loadError}</div>
                  ) : (
                    <ContextClarifyView questions={clarifyQuestions} />
                  )}
                </NodePanel>

                {!isCurrent ? (
                  <NodePanel
                    label="Split"
                    panelId="split"
                    nodeId={node.node_id}
                    expanded={isPanelExpanded(node.node_id, 'split', isCurrent)}
                    onToggle={togglePanel}
                  >
                    <ContextSplitView node={node} nodeRegistry={nodeRegistry} currentNodeId={nodeId} />
                  </NodePanel>
                ) : null}

                {isCurrent && variant === 'audit' && specConfirmed ? (
                  <NodePanel
                    label="Spec"
                    panelId="spec"
                    nodeId={node.node_id}
                    expanded={isPanelExpanded(node.node_id, 'spec', isCurrent)}
                    onToggle={togglePanel}
                  >
                    {!specEntry || specEntry.isLoading ? (
                      <div className={styles.stateLoading}>Loading...</div>
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
            </div>
          )
        })}
      </div>

      <div className={styles.contextFooter} />
    </div>
  )
}
