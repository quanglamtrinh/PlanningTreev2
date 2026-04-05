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
  /** Frame panel: shared chrome (toggle + body) for every node */
  frameChrome?: boolean
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

function isInitNode(node: NodeRecord): boolean {
  return node.is_init_node === true
}

function normalizeShellNodeNumber(rawNumber: string | null | undefined, stripInitPrefix: boolean): string | null {
  const value = String(rawNumber ?? '').trim()
  if (!value) {
    return null
  }
  if (!stripInitPrefix) {
    return value
  }
  const dotIndex = value.indexOf('.')
  if (dotIndex <= -1 || dotIndex >= value.length - 1) {
    return value
  }
  const normalized = value.slice(dotIndex + 1).trim()
  return normalized || null
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

function IconUsers({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <circle cx="8" cy="5.25" r="2.75" stroke="currentColor" strokeWidth="1.25" />
      <path
        d="M3.25 13.25c0-2.35 2.13-4.25 4.75-4.25s4.75 1.9 4.75 4.25"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinecap="round"
      />
    </svg>
  )
}

function IconClipboard({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
      <path
        d="M5.5 2.75h5a.75.75 0 01.75.75V4H4.75V3.5a.75.75 0 01.75-.75zM4 4.75h8a1.25 1.25 0 011.25 1.25v6.5A1.25 1.25 0 0112 13.75H4A1.25 1.25 0 012.75 12.5v-6.5A1.25 1.25 0 014 4.75z"
        stroke="currentColor"
        strokeWidth="1.25"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ContextClarifyView({ questions }: { questions: ClarifyQuestion[] }) {
  if (questions.length === 0) {
    return <div className={styles.stateEmpty}>No clarify questions.</div>
  }

  const [first, ...rest] = questions
  const firstAnswer = resolveAnswer(first)

  return (
    <div className={styles.clarifyDoc}>
      <section className={styles.docSection}>
        <div className={styles.sectionLabelRow}>
          <IconUsers className={styles.sectionLabelIcon} />
          <span className={styles.sectionLabelText}>User story</span>
        </div>
        <div className={styles.userStoryBody}>
          <span className={styles.storyIndex}>01</span>
          <div className={styles.storyContent}>
            <span className={styles.qaQuestion}>
              1. {first.question}
            </span>
            {firstAnswer ? (
              <p className={styles.storyAnswer}>{firstAnswer}</p>
            ) : (
              <span className={styles.qaAnswerEmpty}>Not answered</span>
            )}
          </div>
        </div>
      </section>

      {rest.length > 0 ? (
        <section className={`${styles.docSection} ${styles.docSectionSpaced}`}>
          <div className={styles.sectionLabelRow}>
            <IconClipboard className={styles.sectionLabelIcon} />
            <span className={styles.sectionLabelText}>Functional requirements</span>
          </div>
          <ul className={styles.requirementList}>
            {rest.map((question, index) => {
              const answer = resolveAnswer(question)
              const n = index + 2
              return (
                <li key={question.field_name} className={styles.requirementItem}>
                  <span
                    className={styles.reqCheck}
                    data-checked={answer ? 'true' : 'false'}
                    aria-hidden
                  >
                    {answer ? (
                      <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="8" cy="8" r="8" fill="#059669" />
                        <path
                          d="M4.75 8.35 6.85 10.4 11.35 5.65"
                          stroke="#ffffff"
                          strokeWidth="1.35"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                    ) : (
                      <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                        <circle cx="8" cy="8" r="7.25" stroke="#c4c4c4" strokeWidth="1.35" />
                      </svg>
                    )}
                  </span>
                  <div className={styles.requirementText}>
                    <span className={styles.qaQuestion}>
                      {n}. {question.question}
                    </span>
                    {answer ? (
                      <span className={styles.qaAnswer}>{answer}</span>
                    ) : (
                      <span className={styles.qaAnswerEmpty}>Not answered</span>
                    )}
                  </div>
                </li>
              )
            })}
          </ul>
        </section>
      ) : null}
    </div>
  )
}

function ContextSplitView({
  node,
  nodeRegistry,
  currentNodeId,
  stripInitPrefix,
}: {
  node: NodeRecord
  nodeRegistry: NodeRecord[]
  currentNodeId: string
  stripInitPrefix: boolean
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
        const displayNumber = normalizeShellNodeNumber(child.hierarchical_number, stripInitPrefix)
        return (
          <div key={child.node_id} className={styles.childItem}>
            {displayNumber ? (
              <span className={styles.childNumber}>{displayNumber}</span>
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

function NodePanel({ label, panelId, nodeId, expanded, onToggle, children, frameChrome }: PanelProps) {
  return (
    <div className={`${styles.panel} ${frameChrome ? styles.panelFrame : ''}`}>
      <button
        type="button"
        className={styles.panelToggle}
        aria-expanded={expanded}
        onClick={() => onToggle(nodeId, panelId)}
      >
        <Chevron expanded={expanded} />
        <span className={styles.panelLabel}>{label}</span>
      </button>
      {expanded ? (
        <div className={`${styles.panelBody} ${frameChrome ? styles.framePanelBody : ''}`}>{children}</div>
      ) : null}
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
  const rawChain = useMemo(() => buildAncestorChain(nodeId, nodeRegistry), [nodeId, nodeRegistry])
  const stripInitPrefix = rawChain.length > 0 && isInitNode(rawChain[0])
  const chain = useMemo(() => rawChain.filter((node) => !isInitNode(node)), [rawChain])
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
          const displayNumber = normalizeShellNodeNumber(node.hierarchical_number, stripInitPrefix)
          const frameEntry = frameEntries[`${projectId}::${node.node_id}::frame`]
          const specEntry = frameEntries[`${projectId}::${node.node_id}::spec`]
          const clarifyEntry = clarifyEntries[`${projectId}::${node.node_id}`]
          const clarifyQuestions = clarifyEntry?.clarify?.questions ?? []

          return (
            <div key={node.node_id} className={styles.nodeCardRow}>
              <div className={styles.nodeCardHeader}>
                {displayNumber ? (
                  <span className={styles.nodeNumber}>{displayNumber}</span>
                ) : null}
                <span className={styles.nodeTitle}>{node.title}</span>
                {isCurrent ? <span className={styles.currentBadge}>Current task</span> : null}
              </div>

              <div className={styles.nodeCard}>
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

              <div className={styles.nodeCardBody}>
                <div className={styles.panelList}>
                <NodePanel
                  label="Frame"
                  panelId="frame"
                  nodeId={node.node_id}
                  expanded={isPanelExpanded(node.node_id, 'frame', isCurrent)}
                  onToggle={togglePanel}
                  frameChrome
                >
                  <div className={styles.framePanelInner}>
                    {!frameEntry || frameEntry.isLoading ? (
                      <div className={styles.stateLoading}>Loading...</div>
                    ) : frameEntry.error ? (
                      <div className={styles.stateError}>{frameEntry.error}</div>
                    ) : !frameEntry.content.trim() ? (
                      <div className={styles.stateEmpty}>No frame content yet.</div>
                    ) : (
                      <FrameMarkdownViewer content={frameEntry.content} shellStyle />
                    )}
                  </div>
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
                    <ContextSplitView
                      node={node}
                      nodeRegistry={nodeRegistry}
                      currentNodeId={nodeId}
                      stripInitPrefix={stripInitPrefix}
                    />
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
              </div>
            </div>
          )
        })}
      </div>

      <div className={styles.contextFooter} />
    </div>
  )
}
