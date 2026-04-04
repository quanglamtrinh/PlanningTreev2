import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import type {
  ConversationItemV3,
  ItemStatus,
  PendingUserInputRequestV3,
  PlanActionV3,
  ProcessingState,
  ThreadSnapshotV3,
  ToolItem as ToolItemV2,
  ToolItemV3,
  UserInputAnswerV3,
  UserInputItemV3,
  UserInputQuestionV3,
} from '../../../../api/types'
import { AgentSpinner } from '../../../../components/AgentSpinner'
import { FileChangeToolRow } from '../FileChangeToolRow'
import {
  inferFileWritesFromCommandText,
  inferInlineFileWriteContentFromCommandText,
  toAddedDiffText,
} from '../fileChangeInference'
import { ConversationMarkdown } from '../ConversationMarkdown'
import styles from './MessagesV3.module.css'
import {
  buildToolGroupsV3,
  deriveVisibleMessageStateV3,
  type ReasoningPresentationMetaV3,
  type ToolGroupEntryV3,
} from './messagesV3.utils'
import {
  loadMessagesV3ViewState,
  saveMessagesV3ViewState,
  type MessagesV3ViewState,
} from './messagesV3.viewState'

const SCROLL_THRESHOLD_PX = 120
const MAX_COMMAND_OUTPUT_LINES = 200
const LARGE_COMMAND_OUTPUT_CHAR_THRESHOLD = 600
const LARGE_COMMAND_OUTPUT_LINE_THRESHOLD = 12
const VIEW_STATE_PERSIST_DEBOUNCE_MS = 150
const EMPTY_USER_INPUT_ANSWERS: UserInputAnswerV3[] = []

type PendingRequestStatus = PendingUserInputRequestV3['status']

function normalizeText(value: string | null | undefined): string {
  return String(value ?? '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .trim()
}

function toStatusClassName(status: ItemStatus): string {
  if (status === 'completed' || status === 'answered') {
    return styles.statusCompleted
  }
  if (status === 'in_progress' || status === 'requested' || status === 'answer_submitted') {
    return styles.statusInProgress
  }
  if (status === 'failed' || status === 'stale' || status === 'cancelled') {
    return styles.statusFailed
  }
  return ''
}

function isPendingRequestStatus(status: PendingRequestStatus): boolean {
  return status === 'requested' || status === 'answer_submitted'
}

function buildPlanReadyDismissKey(
  threadId: string | null | undefined,
  planItemId: string | null | undefined,
  revision: number | null | undefined,
): string | null {
  const normalizedThreadId = String(threadId ?? '').trim()
  const normalizedPlanItemId = String(planItemId ?? '').trim()
  if (!normalizedThreadId || !normalizedPlanItemId || revision == null) {
    return null
  }
  return `${normalizedThreadId}:${normalizedPlanItemId}:${revision}`
}

function collectPlanReadyKeys(snapshot: ThreadSnapshotV3 | null): Set<string> {
  const keys = new Set<string>()
  if (!snapshot?.threadId) {
    return keys
  }
  for (const item of snapshot.items) {
    if (item.kind !== 'review') {
      continue
    }
    const metadataKind = String(item.metadata?.v2Kind ?? '').trim()
    if (metadataKind !== 'plan') {
      continue
    }
    const key = buildPlanReadyDismissKey(snapshot.threadId, item.id, item.sequence)
    if (key) {
      keys.add(key)
    }
  }
  const signal = snapshot.uiSignals.planReady
  const signalKey = buildPlanReadyDismissKey(
    snapshot.threadId,
    signal.planItemId,
    signal.revision,
  )
  if (signalKey) {
    keys.add(signalKey)
  }
  return keys
}

function isLargeCommandOutput(item: ToolItemV3): boolean {
  if (item.toolType !== 'commandExecution') {
    return false
  }
  const output = normalizeText(item.outputText)
  if (!output) {
    return false
  }
  const lineCount = output.split('\n').length
  return (
    output.length >= LARGE_COMMAND_OUTPUT_CHAR_THRESHOLD ||
    lineCount >= LARGE_COMMAND_OUTPUT_LINE_THRESHOLD
  )
}

/** Keeps persisted expand state from being cleared by auto-expand/collapse sync on thread load. */
function primeManualExpandedIdsFromSavedView(
  savedExpandedIds: readonly string[],
  snap: ThreadSnapshotV3 | null,
  threadId: string,
  target: Set<string>,
): void {
  if (!snap || snap.threadId !== threadId) {
    return
  }
  const itemById = new Map(snap.items.map((i) => [i.id, i]))
  const derived = deriveVisibleMessageStateV3(snap)
  for (const id of savedExpandedIds) {
    const item = itemById.get(id)
    if (!item) {
      continue
    }
    if (item.kind === 'tool') {
      if (item.toolType === 'commandExecution') {
        const shouldAutoExpand = item.status === 'in_progress' || isLargeCommandOutput(item)
        if (!shouldAutoExpand) {
          target.add(id)
        }
      } else {
        const hasArguments = Boolean(normalizeText(item.argumentsText))
        const hasOutput = Boolean(normalizeText(item.outputText))
        const hasFiles = item.outputFiles.length > 0
        if (hasArguments || hasOutput || hasFiles) {
          target.add(id)
        }
      }
      continue
    }
    if (item.kind === 'reasoning') {
      const meta = derived.reasoningMetaById.get(id)
      const shouldAutoExpand =
        item.status === 'in_progress' && Boolean(meta?.visibleDetail)
      if (!shouldAutoExpand) {
        target.add(id)
      }
    }
  }
}

function isNearBottom(node: HTMLDivElement): boolean {
  return node.scrollHeight - node.scrollTop - node.clientHeight <= SCROLL_THRESHOLD_PX
}

function commandRanLabel(status: ItemStatus): string {
  return status === 'in_progress' ? 'Running' : 'Ran'
}

function trailingCommandOutput(outputText: string): string {
  const normalized = outputText.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const lines = normalized.split('\n')
  if (lines.length <= MAX_COMMAND_OUTPUT_LINES) {
    return normalized
  }
  return lines.slice(-MAX_COMMAND_OUTPUT_LINES).join('\n')
}

function looksLikeDiffText(text: string): boolean {
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  return /^(?:\+\+\+|---|@@)/m.test(normalized) || /^[+-][^\r\n]*/m.test(normalized)
}

function toolInferenceSource(item: ToolItemV3): string {
  return [item.argumentsText, item.title, item.toolName, item.outputText]
    .map((part) => normalizeText(part))
    .filter(Boolean)
    .join('\n')
}

function inferredFilesForTool(item: ToolItemV3): ToolItemV3['outputFiles'] {
  const inferred = inferFileWritesFromCommandText(toolInferenceSource(item))
  return inferred.map((file) => ({
    path: file.path,
    changeType: file.changeType,
    summary: file.summary,
  }))
}

function inferredFileChangeOutputTextForTool(item: ToolItemV3): string {
  const inferredContent = inferInlineFileWriteContentFromCommandText(toolInferenceSource(item))
  if (inferredContent) {
    return toAddedDiffText(inferredContent)
  }

  if (!normalizeText(item.outputText)) {
    return item.outputText
  }

  if (item.toolType === 'commandExecution' && !looksLikeDiffText(item.outputText)) {
    return toAddedDiffText(item.outputText)
  }

  return item.outputText
}

function effectiveUserInputStatus(
  item: UserInputItemV3,
  requestByRequestId: Map<string, PendingUserInputRequestV3>,
): PendingRequestStatus {
  const request = requestByRequestId.get(item.requestId)
  if (request) {
    return request.status
  }
  if (
    item.status === 'requested' ||
    item.status === 'answer_submitted' ||
    item.status === 'answered' ||
    item.status === 'stale'
  ) {
    return item.status
  }
  return 'requested'
}

function groupAnswersByQuestion(answers: UserInputAnswerV3[]): Record<string, string[]> {
  const grouped: Record<string, string[]> = {}
  for (const answer of answers) {
    grouped[answer.questionId] = [...(grouped[answer.questionId] ?? []), answer.value]
  }
  return grouped
}

function buildAnswerPayload(
  questions: UserInputQuestionV3[],
  draftAnswers: Record<string, string[]>,
): UserInputAnswerV3[] {
  const answers: UserInputAnswerV3[] = []
  for (const question of questions) {
    const values = draftAnswers[question.id] ?? []
    if (!values.length) {
      continue
    }
    for (const value of values) {
      const matchingOption = question.options.find(
        (option) => value === option.label || value === option.description,
      )
      answers.push({
        questionId: question.id,
        value,
        label: matchingOption?.label ?? null,
      })
    }
  }
  return answers
}

function requestByRequestId(
  pendingRequests: PendingUserInputRequestV3[],
): Map<string, PendingUserInputRequestV3> {
  const next = new Map<string, PendingUserInputRequestV3>()
  for (const request of pendingRequests) {
    next.set(request.requestId, request)
  }
  return next
}

function messageIsPlanSupersedingUserMessage(
  snapshot: ThreadSnapshotV3 | null,
  revision: number | null,
): boolean {
  if (!snapshot || revision == null) {
    return false
  }
  return snapshot.items.some(
    (item) =>
      item.kind === 'message' &&
      item.role === 'user' &&
      Number(item.sequence) > Number(revision),
  )
}

function toViewState(
  expandedItemIds: Set<string>,
  collapsedToolGroupIds: Set<string>,
  dismissedPlanReadyKeys: Set<string>,
): MessagesV3ViewState {
  return {
    schemaVersion: 1,
    expandedItemIds: [...expandedItemIds],
    collapsedToolGroupIds: [...collapsedToolGroupIds],
    dismissedPlanReadyKeys: [...dismissedPlanReadyKeys],
    updatedAt: new Date().toISOString(),
  }
}

function formatDurationV3(durationMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(durationMs / 1000))
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

function WorkingIndicatorV3({
  processingState,
  activeTurnId,
  lastCompletedAt,
  lastDurationMs,
}: {
  processingState: ProcessingState
  activeTurnId: string | null
  lastCompletedAt?: number | null
  lastDurationMs?: number | null
}) {
  if (processingState === 'running' && activeTurnId) {
    return (
      <div className={styles.row} data-testid="conversation-working-indicator">
        <div className={styles.rowRail}>
          <div className={styles.workingIndicator}>
            <AgentSpinner />
          </div>
        </div>
      </div>
    )
  }

  if (processingState === 'waiting_user_input') {
    return (
      <div className={styles.row} data-testid="conversation-working-indicator">
        <div className={styles.rowRail}>
          <div className={styles.workingIndicator}>
            <span className={styles.workingText}>Waiting for user input.</span>
          </div>
        </div>
      </div>
    )
  }

  if (lastCompletedAt != null && lastDurationMs != null && Date.now() - lastCompletedAt < 4000) {
    return (
      <div className={styles.row} data-testid="conversation-working-indicator">
        <div className={styles.rowRail}>
          <div className={styles.workingIndicator}>
            <span className={styles.workingText}>Completed.</span>
            <span className={styles.workingMeta}>{formatDurationV3(lastDurationMs)}</span>
          </div>
        </div>
      </div>
    )
  }

  return null
}

function CommandOutputViewportV3({
  itemId,
  outputText,
  onRequestAutoScroll,
}: {
  itemId: string
  outputText: string
  onRequestAutoScroll?: () => void
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const pinnedRef = useRef(true)
  const [, setPinnedVersion] = useState(0)

  const visibleOutput = useMemo(() => trailingCommandOutput(outputText), [outputText])

  const updatePinnedState = useCallback(() => {
    const viewport = viewportRef.current
    if (!viewport) {
      return
    }
    const isPinned = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= 8
    pinnedRef.current = isPinned
    setPinnedVersion((current) => current + 1)
  }, [])

  useLayoutEffect(() => {
    const viewport = viewportRef.current
    if (!viewport || !pinnedRef.current) {
      return
    }
    viewport.scrollTop = viewport.scrollHeight
    onRequestAutoScroll?.()
  }, [onRequestAutoScroll, visibleOutput])

  return (
    <div
      ref={viewportRef}
      className={styles.commandViewport}
      data-testid={`conversation-v3-tool-output-${itemId}`}
      onScroll={updatePinnedState}
    >
      <pre className={styles.commandPre}>{visibleOutput}</pre>
    </div>
  )
}

function MessageRowV3({ item }: { item: Extract<ConversationItemV3, { kind: 'message' }> }) {
  const roleClass =
    item.role === 'user'
      ? styles.rowMessageUser
      : item.role === 'system'
        ? styles.rowMessageSystem
        : styles.rowMessageAssistant

  const bubbleClass =
    item.role === 'user'
      ? styles.messageBubbleUser
      : item.role === 'system'
        ? styles.messageBubbleSystem
        : styles.messageBubbleAssistant

  return (
    <article className={`${styles.row} ${roleClass}`} data-testid="conversation-v3-item-message">
      <div className={styles.rowRail}>
        <div
          className={`${styles.messageShell} ${item.role === 'user' ? styles.messageShellUser : styles.messageShellAssistant}`}
        >
          <div className={`${styles.messageBubble} ${bubbleClass}`}>
            <ConversationMarkdown content={item.text} />
          </div>
        </div>
      </div>
    </article>
  )
}

function ReasoningRowV3({
  item,
  meta,
  isExpanded,
  onToggle,
}: {
  item: Extract<ConversationItemV3, { kind: 'reasoning' }>
  meta?: ReasoningPresentationMetaV3
  isExpanded: boolean
  onToggle: (itemId: string) => void
}) {
  return (
    <article className={`${styles.row} ${styles.reasoningRow}`} data-testid="conversation-v3-item-reasoning">
      <div className={styles.reasoningRail}>
        <div className={styles.reasoningInner}>
          <div className={styles.reasoningHeader}>
            <span className={styles.reasoningKicker}>Reasoning update</span>
            {meta?.visibleDetail ? (
              <button type="button" className={styles.reasoningExpandToggle} onClick={() => onToggle(item.id)}>
                {isExpanded ? 'Collapse' : 'Expand'}
              </button>
            ) : null}
          </div>
          {meta?.visibleSummary ? <div className={styles.reasoningBody}>{meta.visibleSummary}</div> : null}
          {isExpanded && meta?.visibleDetail ? (
            <pre className={`${styles.plainPre} ${styles.reasoningDetailPre}`}>{meta.visibleDetail}</pre>
          ) : null}
        </div>
      </div>
    </article>
  )
}

function CommandToolRowV3({
  item,
  isExpanded,
  onToggle,
  onRequestAutoScroll,
}: {
  item: Extract<ConversationItemV3, { kind: 'tool' }>
  isExpanded: boolean
  onToggle: (itemId: string) => void
  onRequestAutoScroll?: () => void
}) {
  const headline =
    normalizeText(item.argumentsText) ||
    normalizeText(item.title) ||
    normalizeText(item.toolName) ||
    'Running command'
  const hasOutput = Boolean(normalizeText(item.outputText))
  const hasFiles = item.outputFiles.length > 0
  const hasBody = Boolean(normalizeText(item.argumentsText) || hasOutput || hasFiles)
  const showBody = !hasBody || isExpanded
  const ranLabel = commandRanLabel(item.status)

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-tool">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.commandCard}`}>
          <header className={styles.commandCardHeader}>
            <div className={styles.commandCardHeaderLeft}>
              <span className={styles.commandCardEyebrow}>Command</span>
              <span className={styles.commandHeaderStatusPill}>{item.status.replace(/_/g, ' ')}</span>
            </div>
            {hasBody ? (
              <button
                type="button"
                className={styles.commandExpandToggle}
                onClick={() => onToggle(item.id)}
                aria-expanded={showBody}
              >
                {showBody ? 'Collapse' : 'Expand'}
              </button>
            ) : null}
          </header>

          <div className={styles.terminalZone}>
            <div
              className={`${styles.commandLineBar} ${
                showBody ? styles.commandLineBarExpanded : styles.commandLineBarCollapsed
              }`}
            >
              <span className={styles.commandRanLabel}>{ranLabel}</span>
              <span
                className={showBody ? styles.commandLineTextExpanded : styles.commandLineTextCollapsed}
              >
                {headline}
              </span>
            </div>

            {showBody ? (
              <>
                <div className={styles.commandOutputHeader}>
                  <span className={styles.commandOutputEyebrow}>Output</span>
                  <span
                    className={`${styles.exitPill} ${
                      item.exitCode === 0
                        ? styles.exitPillSuccess
                        : item.exitCode != null
                          ? styles.exitPillFailure
                          : item.status === 'in_progress'
                            ? styles.exitPillRunning
                            : styles.exitPillMuted
                    }`}
                  >
                    <span className={styles.exitPillDot} aria-hidden />
                    {item.exitCode != null
                      ? `exit ${item.exitCode}`
                      : item.status === 'in_progress'
                        ? 'Running'
                        : 'exit -'}
                  </span>
                </div>

                {hasOutput ? (
                  <CommandOutputViewportV3
                    itemId={item.id}
                    outputText={item.outputText}
                    onRequestAutoScroll={onRequestAutoScroll}
                  />
                ) : null}
              </>
            ) : null}
          </div>

          {showBody && hasFiles ? (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Files</div>
              <div className={styles.fileList}>
                {item.outputFiles.map((file) => (
                  <div key={`${file.path}-${file.changeType}`} className={styles.fileItem}>
                    <div className={styles.fileMeta}>
                      <span className={styles.statusPill}>{file.changeType}</span>
                      <code>{file.path}</code>
                    </div>
                    {file.summary ? <div className={styles.subtleText}>{file.summary}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {showBody && !hasBody ? (
            <div className={styles.subtleText}>
              {item.status === 'completed'
                ? 'Command finished without visible output.'
                : 'Waiting for command output...'}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  )
}

function ToolRowV3({
  item,
  isExpanded,
  onToggle,
  onRequestAutoScroll,
}: {
  item: Extract<ConversationItemV3, { kind: 'tool' }>
  isExpanded: boolean
  onToggle: (itemId: string) => void
  onRequestAutoScroll?: () => void
}) {
  const inferredFiles = useMemo(() => inferredFilesForTool(item), [item])
  const effectiveFiles = item.outputFiles.length ? item.outputFiles : inferredFiles
  const effectiveOutputText = useMemo(() => inferredFileChangeOutputTextForTool(item), [item])

  if (item.toolType === 'fileChange' || effectiveFiles.length > 0) {
    const fileChangeItem: ToolItemV2 = {
      ...item,
      kind: 'tool',
      toolType: 'fileChange',
      outputText: effectiveOutputText,
      outputFiles: effectiveFiles,
    }
    return (
      <FileChangeToolRow
        item={fileChangeItem}
        isExpanded={isExpanded}
        onToggle={onToggle}
        dataTestId="conversation-v3-item-tool"
      />
    )
  }

  if (item.toolType === 'commandExecution') {
    return (
      <CommandToolRowV3
        item={item}
        isExpanded={isExpanded}
        onToggle={onToggle}
        onRequestAutoScroll={onRequestAutoScroll}
      />
    )
  }

  const headline = normalizeText(item.title) || normalizeText(item.toolName) || 'Tool activity'
  const hasArguments = Boolean(normalizeText(item.argumentsText))
  const hasOutput = Boolean(normalizeText(item.outputText))
  const hasFiles = item.outputFiles.length > 0
  const hasBody = hasArguments || hasOutput || hasFiles
  const showBody = !hasBody || isExpanded

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-tool">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection}`}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardEyebrow}>Tool</div>
              <div className={styles.cardTitleRow}>
                <h3 className={styles.cardTitle}>{headline}</h3>
                {hasBody ? (
                  <button type="button" className={styles.inlineToggle} onClick={() => onToggle(item.id)}>
                    {showBody ? 'Collapse' : 'Expand'}
                  </button>
                ) : null}
              </div>
            </div>
            <div className={styles.cardMeta}>
              <span className={`${styles.statusPill} ${toStatusClassName(item.status)}`}>{item.status}</span>
              {item.toolName ? <span>{item.toolName}</span> : null}
              {item.exitCode != null ? <span>exit {item.exitCode}</span> : null}
            </div>
          </div>

          {showBody && hasArguments ? (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Arguments</div>
              <pre className={styles.plainPre}>{item.argumentsText}</pre>
            </div>
          ) : null}

          {showBody && hasOutput ? (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Output</div>
              <pre className={styles.plainPre}>{item.outputText}</pre>
            </div>
          ) : null}

          {showBody && hasFiles ? (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Files</div>
              <div className={styles.fileList}>
                {item.outputFiles.map((file) => (
                  <div key={`${file.path}-${file.changeType}`} className={styles.fileItem}>
                    <div className={styles.fileMeta}>
                      <span className={styles.statusPill}>{file.changeType}</span>
                      <code>{file.path}</code>
                    </div>
                    {file.summary ? <div className={styles.subtleText}>{file.summary}</div> : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {showBody && !hasBody ? (
            <div className={styles.subtleText}>
              {item.status === 'completed' ? 'Tool completed.' : 'Waiting for tool output...'}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  )
}

function ReviewRowV3({ item }: { item: Extract<ConversationItemV3, { kind: 'review' }> }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-review">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.reviewCard}`}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardEyebrow}>Review</div>
              <h3 className={styles.cardTitle}>{item.title ?? 'Review summary'}</h3>
            </div>
            <span className={`${styles.statusPill} ${toStatusClassName(item.status)}`}>{item.status}</span>
          </div>
          <ConversationMarkdown content={item.text} />
        </div>
      </div>
    </article>
  )
}

function ExploreRowV3({ item }: { item: Extract<ConversationItemV3, { kind: 'explore' }> }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-explore">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.exploreCard}`}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardEyebrow}>Explore</div>
              <h3 className={styles.cardTitle}>{item.title ?? 'Explore'}</h3>
            </div>
            <span className={`${styles.statusPill} ${toStatusClassName(item.status)}`}>{item.status}</span>
          </div>
          <ConversationMarkdown content={item.text} />
        </div>
      </div>
    </article>
  )
}

function DiffRowV3({ item }: { item: Extract<ConversationItemV3, { kind: 'diff' }> }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-diff">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.diffCard}`}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardEyebrow}>Diff</div>
              <h3 className={styles.cardTitle}>{item.title ?? 'File changes'}</h3>
            </div>
            <span className={`${styles.statusPill} ${toStatusClassName(item.status)}`}>{item.status}</span>
          </div>
          {item.summaryText ? <div className={styles.subtleText}>{item.summaryText}</div> : null}

          {item.files.length ? (
            <div className={styles.fileList}>
              {item.files.map((file) => (
                <div key={`${file.path}-${file.changeType}`} className={styles.fileItem}>
                  <div className={styles.fileMeta}>
                    <span className={styles.statusPill}>{file.changeType}</span>
                    <code>{file.path}</code>
                  </div>
                  {file.summary ? <div className={styles.subtleText}>{file.summary}</div> : null}
                </div>
              ))}
            </div>
          ) : null}
        </div>
      </div>
    </article>
  )
}

function StatusRowV3({ item }: { item: Extract<ConversationItemV3, { kind: 'status' }> }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-status">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.statusCard}`}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardEyebrow}>Status</div>
              <h3 className={styles.cardTitle}>{item.label || item.code || 'Status'}</h3>
            </div>
            <span className={`${styles.statusPill} ${toStatusClassName(item.status)}`}>{item.status}</span>
          </div>
          {item.detail ? <div className={styles.subtleText}>{item.detail}</div> : null}
        </div>
      </div>
    </article>
  )
}

function ErrorRowV3({ item }: { item: Extract<ConversationItemV3, { kind: 'error' }> }) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-error">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.errorCard}`}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardEyebrow}>Error</div>
              <h3 className={styles.cardTitle}>{item.title || item.code || 'Error'}</h3>
            </div>
            <span className={`${styles.statusPill} ${toStatusClassName(item.status)}`}>{item.status}</span>
          </div>
          <div className={styles.subtleText}>{item.message}</div>
        </div>
      </div>
    </article>
  )
}

function UserInputInlineRowV3({
  item,
  status,
  answers,
}: {
  item: Extract<ConversationItemV3, { kind: 'userInput' }>
  status: PendingRequestStatus
  answers: UserInputAnswerV3[]
}) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-userInput-inline">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.userInputInlineCard}`}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardEyebrow}>User Input</div>
              <h3 className={styles.cardTitle}>{item.title ?? 'Input request'}</h3>
            </div>
            <span className={`${styles.statusPill} ${toStatusClassName(status)}`}>{status}</span>
          </div>
          <div className={styles.subtleText}>
            {answers.length
              ? `${answers.length} answers recorded.`
              : status === 'stale'
                ? 'Previous request became stale.'
                : 'No answers recorded.'}
          </div>
        </div>
      </div>
    </article>
  )
}

function PendingUserInputCardV3({
  request,
  item,
  onResolve,
}: {
  request: PendingUserInputRequestV3
  item: Extract<ConversationItemV3, { kind: 'userInput' }> | null
  onResolve: (requestId: string, answers: UserInputAnswerV3[]) => Promise<void> | void
}) {
  const currentAnswers =
    request.answers.length > 0
      ? request.answers
      : item?.answers ?? EMPTY_USER_INPUT_ANSWERS
  const [draftAnswers, setDraftAnswers] = useState<Record<string, string[]>>(() =>
    groupAnswersByQuestion(currentAnswers),
  )

  useEffect(() => {
    setDraftAnswers(groupAnswersByQuestion(currentAnswers))
  }, [item?.id, currentAnswers])

  const questions = item?.questions ?? []
  const answerPayload = useMemo(
    () => buildAnswerPayload(questions, draftAnswers),
    [draftAnswers, questions],
  )
  const isSubmitting = request.status === 'answer_submitted'
  const canSubmit = request.status === 'requested' && answerPayload.length > 0

  return (
    <article
      className={`${styles.row} ${styles.rowCard}`}
      data-testid={`conversation-v3-pending-user-input-${request.requestId}`}
    >
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.pendingUserInputCard}`}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardEyebrow}>User Input</div>
              <h3 className={styles.cardTitle}>{item?.title ?? 'Additional input needed'}</h3>
            </div>
            <span className={`${styles.statusPill} ${toStatusClassName(request.status)}`}>
              {request.status}
            </span>
          </div>

          {questions.length > 0 ? (
            <div className={styles.questionList}>
              {questions.map((question) => {
                const selectedValues = draftAnswers[question.id] ?? []
                return (
                  <div key={question.id} className={styles.questionCard}>
                    {question.header ? <div className={styles.questionHeader}>{question.header}</div> : null}
                    <div className={styles.questionPrompt}>{question.prompt}</div>
                    {question.inputType === 'text' ? (
                      <textarea
                        className={styles.textInput}
                        disabled={isSubmitting}
                        value={selectedValues[0] ?? ''}
                        onChange={(event) =>
                          setDraftAnswers((current) => ({
                            ...current,
                            [question.id]: event.target.value.trim() ? [event.target.value] : [],
                          }))
                        }
                      />
                    ) : (
                      <div className={styles.optionList}>
                        {question.options.map((option) => {
                          const checked = selectedValues.includes(option.label)
                          const controlType =
                            question.inputType === 'multi_select' ? 'checkbox' : 'radio'
                          return (
                            <label key={option.label} className={styles.optionLabel}>
                              <input
                                type={controlType}
                                name={`${request.requestId}:${question.id}`}
                                disabled={isSubmitting}
                                checked={checked}
                                onChange={(event) => {
                                  const isChecked = event.target.checked
                                  setDraftAnswers((current) => {
                                    const existing = current[question.id] ?? []
                                    if (question.inputType === 'single_select') {
                                      return {
                                        ...current,
                                        [question.id]: isChecked ? [option.label] : [],
                                      }
                                    }
                                    return {
                                      ...current,
                                      [question.id]: isChecked
                                        ? [...existing, option.label]
                                        : existing.filter((value) => value !== option.label),
                                    }
                                  })
                                }}
                              />
                              <span className={styles.optionText}>
                                <span>{option.label}</span>
                                {option.description ? (
                                  <span className={styles.optionDescription}>{option.description}</span>
                                ) : null}
                              </span>
                            </label>
                          )
                        })}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          ) : (
            <div className={styles.subtleText}>Waiting for question payload.</div>
          )}

          {currentAnswers.length > 0 ? (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Current answers</div>
              <div className={styles.answerList}>
                {currentAnswers.map((answer, index) => (
                  <div
                    key={`${answer.questionId}-${answer.value}-${index}`}
                    className={styles.answerItem}
                  >
                    <div className={styles.subtleText}>
                      <strong>{answer.questionId}</strong>: {answer.label ?? answer.value}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className={styles.actionRow}>
            <button
              type="button"
              className={styles.primaryButton}
              disabled={!canSubmit || isSubmitting}
              onClick={() => void onResolve(request.requestId, answerPayload)}
            >
              {isSubmitting ? 'Submitting...' : 'Submit answers'}
            </button>
          </div>
        </div>
      </div>
    </article>
  )
}

function PlanReadyFollowupCardV3({
  planItemId,
  revision,
  isSending,
  onDismiss,
  onPlanAction,
}: {
  planItemId: string
  revision: number
  isSending: boolean
  onDismiss: () => void
  onPlanAction: (action: PlanActionV3, planItemId: string, revision: number) => Promise<void> | void
}) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-plan-ready-card">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.planReadyCard}`}>
          <div className={styles.cardHeader}>
            <div>
              <div className={styles.cardEyebrow}>Plan Ready</div>
              <h3 className={styles.cardTitle}>Choose a follow-up action</h3>
            </div>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={onDismiss}
              disabled={isSending}
            >
              Dismiss
            </button>
          </div>
          <div className={styles.subtleText}>
            Plan item <code>{planItemId}</code> at revision <code>{revision}</code> is ready.
          </div>
          <div className={styles.actionRow}>
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={isSending}
              onClick={() => void onPlanAction('send_changes', planItemId, revision)}
            >
              Send changes
            </button>
            <button
              type="button"
              className={styles.primaryButton}
              disabled={isSending}
              onClick={() => void onPlanAction('implement_plan', planItemId, revision)}
            >
              Implement this plan
            </button>
          </div>
        </div>
      </div>
    </article>
  )
}

function renderItemRowV3({
  item,
  requestMapByRequestId,
  reasoningMeta,
  expandedItemIds,
  onToggleExpanded,
  onRequestAutoScroll,
}: {
  item: ConversationItemV3
  requestMapByRequestId: Map<string, PendingUserInputRequestV3>
  reasoningMeta?: ReasoningPresentationMetaV3
  expandedItemIds: Set<string>
  onToggleExpanded: (itemId: string) => void
  onRequestAutoScroll: () => void
}) {
  if (item.kind === 'message') {
    return <MessageRowV3 item={item} />
  }
  if (item.kind === 'reasoning') {
    return (
      <ReasoningRowV3
        item={item}
        meta={reasoningMeta}
        isExpanded={expandedItemIds.has(item.id)}
        onToggle={onToggleExpanded}
      />
    )
  }
  if (item.kind === 'tool') {
    return (
      <ToolRowV3
        item={item}
        isExpanded={expandedItemIds.has(item.id)}
        onToggle={onToggleExpanded}
        onRequestAutoScroll={onRequestAutoScroll}
      />
    )
  }
  if (item.kind === 'review') {
    return <ReviewRowV3 item={item} />
  }
  if (item.kind === 'diff') {
    return <DiffRowV3 item={item} />
  }
  if (item.kind === 'explore') {
    return <ExploreRowV3 item={item} />
  }
  if (item.kind === 'status') {
    return <StatusRowV3 item={item} />
  }
  if (item.kind === 'error') {
    return <ErrorRowV3 item={item} />
  }
  if (item.kind === 'userInput') {
    const request = requestMapByRequestId.get(item.requestId)
    const status = request?.status ?? effectiveUserInputStatus(item, requestMapByRequestId)
    const answers = request?.answers.length ? request.answers : item.answers
    return <UserInputInlineRowV3 item={item} status={status} answers={answers} />
  }
  return null
}

export function MessagesV3({
  snapshot,
  isLoading,
  isSending = false,
  prefix,
  suffix,
  onResolveUserInput,
  onPlanAction,
  lastCompletedAt,
  lastDurationMs,
}: {
  snapshot: ThreadSnapshotV3 | null
  isLoading: boolean
  isSending?: boolean
  prefix?: ReactNode
  suffix?: ReactNode
  onResolveUserInput: (requestId: string, answers: UserInputAnswerV3[]) => Promise<void> | void
  onPlanAction?: (
    action: PlanActionV3,
    planItemId: string,
    revision: number,
  ) => Promise<void> | void
  lastCompletedAt?: number | null
  lastDurationMs?: number | null
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const autoScrollRef = useRef(true)
  const manuallyToggledExpandedRef = useRef<Set<string>>(new Set())
  const manuallyToggledGroupsRef = useRef<Set<string>>(new Set())
  const snapshotRef = useRef(snapshot)
  snapshotRef.current = snapshot

  const [expandedItemIds, setExpandedItemIds] = useState<Set<string>>(new Set())
  const [collapsedToolGroupIds, setCollapsedToolGroupIds] = useState<Set<string>>(new Set())
  const [dismissedPlanReadyKeys, setDismissedPlanReadyKeys] = useState<Set<string>>(new Set())

  const threadId = snapshot?.threadId ?? null
  const pendingRequests = snapshot?.uiSignals.activeUserInputRequests ?? []
  const requestMapByRequestId = useMemo(() => requestByRequestId(pendingRequests), [pendingRequests])

  const itemById = useMemo(() => {
    const map = new Map<string, ConversationItemV3>()
    for (const item of snapshot?.items ?? []) {
      map.set(item.id, item)
    }
    return map
  }, [snapshot?.items])

  const userInputItemByRequestId = useMemo(() => {
    const map = new Map<string, Extract<ConversationItemV3, { kind: 'userInput' }>>()
    for (const item of snapshot?.items ?? []) {
      if (item.kind === 'userInput') {
        map.set(item.requestId, item)
      }
    }
    return map
  }, [snapshot?.items])

  const pendingRequestCards = useMemo(
    () =>
      [...pendingRequests]
        .filter((request) => isPendingRequestStatus(request.status))
        .sort(
          (left, right) =>
            left.createdAt.localeCompare(right.createdAt) ||
            left.requestId.localeCompare(right.requestId),
        ),
    [pendingRequests],
  )

  const visibleState = useMemo(() => deriveVisibleMessageStateV3(snapshot), [snapshot])
  const visibleItems = useMemo(
    () =>
      visibleState.visibleItems.filter((item) => {
        if (item.kind !== 'userInput') {
          return true
        }
        const status = effectiveUserInputStatus(item, requestMapByRequestId)
        return !isPendingRequestStatus(status)
      }),
    [requestMapByRequestId, visibleState.visibleItems],
  )
  const groupedEntries = useMemo(() => buildToolGroupsV3(visibleItems), [visibleItems])

  const requestAutoScroll = useCallback(() => {
    const container = containerRef.current
    const shouldScroll = autoScrollRef.current || (container ? isNearBottom(container) : true)
    if (!shouldScroll) {
      return
    }
    if (container) {
      container.scrollTop = container.scrollHeight
      return
    }
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [])

  const updateAutoScroll = useCallback(() => {
    if (!containerRef.current) {
      return
    }
    autoScrollRef.current = isNearBottom(containerRef.current)
  }, [])

  useLayoutEffect(() => {
    autoScrollRef.current = true
    manuallyToggledExpandedRef.current = new Set()
    manuallyToggledGroupsRef.current = new Set()
    if (!threadId) {
      setExpandedItemIds(new Set())
      setCollapsedToolGroupIds(new Set())
      setDismissedPlanReadyKeys(new Set())
      return
    }
    const saved = loadMessagesV3ViewState(threadId)
    setExpandedItemIds(new Set(saved.expandedItemIds))
    setCollapsedToolGroupIds(new Set(saved.collapsedToolGroupIds))
    setDismissedPlanReadyKeys(new Set(saved.dismissedPlanReadyKeys))
    primeManualExpandedIdsFromSavedView(
      saved.expandedItemIds,
      snapshotRef.current,
      threadId,
      manuallyToggledExpandedRef.current,
    )
  }, [threadId])

  useEffect(() => {
    const visibleItemIds = new Set(visibleItems.map((item) => item.id))
    setExpandedItemIds((previous) => {
      const next = new Set([...previous].filter((id) => visibleItemIds.has(id)))
      const unchanged = next.size === previous.size && [...next].every((id) => previous.has(id))
      return unchanged ? previous : next
    })
  }, [visibleItems])

  useEffect(() => {
    const visibleGroupIds = new Set(
      groupedEntries
        .filter(
          (entry): entry is Extract<ToolGroupEntryV3, { kind: 'toolGroup' }> =>
            entry.kind === 'toolGroup',
        )
        .map((entry) => entry.group.id),
    )
    setCollapsedToolGroupIds((previous) => {
      const next = new Set([...previous].filter((id) => visibleGroupIds.has(id)))
      const unchanged = next.size === previous.size && [...next].every((id) => previous.has(id))
      return unchanged ? previous : next
    })
  }, [groupedEntries])

  useEffect(() => {
    const allowedKeys = collectPlanReadyKeys(snapshot)
    setDismissedPlanReadyKeys((previous) => {
      const next = new Set([...previous].filter((key) => allowedKeys.has(key)))
      const unchanged = next.size === previous.size && [...next].every((key) => previous.has(key))
      return unchanged ? previous : next
    })
  }, [snapshot])

  useEffect(() => {
    setExpandedItemIds((previous) => {
      const next = new Set(previous)
      let changed = false
      for (const item of visibleItems) {
        if (manuallyToggledExpandedRef.current.has(item.id)) {
          continue
        }
        if (item.kind === 'tool') {
          const shouldExpand = item.status === 'in_progress' || isLargeCommandOutput(item)
          if (shouldExpand && !next.has(item.id)) {
            next.add(item.id)
            changed = true
          } else if (!shouldExpand && next.has(item.id)) {
            next.delete(item.id)
            changed = true
          }
          continue
        }
        if (item.kind === 'reasoning') {
          const shouldExpand =
            item.status === 'in_progress' &&
            Boolean(visibleState.reasoningMetaById.get(item.id)?.visibleDetail)
          if (shouldExpand && !next.has(item.id)) {
            next.add(item.id)
            changed = true
          } else if (!shouldExpand && next.has(item.id)) {
            next.delete(item.id)
            changed = true
          }
        }
      }
      return changed ? next : previous
    })
  }, [visibleItems, visibleState.reasoningMetaById])

  useEffect(() => {
    if (!threadId) {
      return
    }
    const persistTimer = globalThis.setTimeout(() => {
      saveMessagesV3ViewState(
        threadId,
        toViewState(expandedItemIds, collapsedToolGroupIds, dismissedPlanReadyKeys),
      )
    }, VIEW_STATE_PERSIST_DEBOUNCE_MS)
    return () => globalThis.clearTimeout(persistTimer)
  }, [collapsedToolGroupIds, dismissedPlanReadyKeys, expandedItemIds, threadId])

  const toggleExpanded = useCallback((itemId: string) => {
    manuallyToggledExpandedRef.current.add(itemId)
    setExpandedItemIds((previous) => {
      const next = new Set(previous)
      if (next.has(itemId)) {
        next.delete(itemId)
      } else {
        next.add(itemId)
      }
      return next
    })
  }, [])

  const toggleToolGroup = useCallback((groupId: string) => {
    manuallyToggledGroupsRef.current.add(groupId)
    setCollapsedToolGroupIds((previous) => {
      const next = new Set(previous)
      if (next.has(groupId)) {
        next.delete(groupId)
      } else {
        next.add(groupId)
      }
      return next
    })
  }, [])

  const scrollKey = useMemo(() => {
    const itemKey = visibleItems
      .map((item) => `${item.id}:${item.updatedAt}:${item.status}`)
      .join('|')
    const pendingKey = pendingRequests
      .map(
        (request) =>
          `${request.requestId}:${request.status}:${request.submittedAt ?? ''}:${request.resolvedAt ?? ''}`,
      )
      .join('|')
    const plan = snapshot?.uiSignals.planReady
    const planKey = `${plan?.planItemId ?? ''}:${plan?.revision ?? ''}:${String(plan?.ready ?? false)}:${String(plan?.failed ?? false)}`
    return `${itemKey}::${pendingKey}::${planKey}`
  }, [pendingRequests, snapshot?.uiSignals.planReady, visibleItems])

  useLayoutEffect(() => {
    const container = containerRef.current
    const shouldScroll = autoScrollRef.current || (container ? isNearBottom(container) : true)
    if (!shouldScroll) {
      return
    }
    if (container) {
      container.scrollTop = container.scrollHeight
      return
    }
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [scrollKey, snapshot?.activeTurnId, snapshot?.processingState, threadId])

  const planReadySignal = snapshot?.uiSignals.planReady
  const planReadyDismissKey = buildPlanReadyDismissKey(
    threadId,
    planReadySignal?.planItemId ?? null,
    planReadySignal?.revision ?? null,
  )
  const hasPlanRevisionItem =
    planReadySignal?.planItemId != null &&
    planReadySignal.revision != null &&
    itemById.get(planReadySignal.planItemId)?.sequence === planReadySignal.revision
  const hasBlockingPendingRequest = pendingRequests.some((request) =>
    isPendingRequestStatus(request.status),
  )
  const supersededByUserMessage = messageIsPlanSupersedingUserMessage(
    snapshot,
    planReadySignal?.revision ?? null,
  )
  const showPlanReadyCard =
    Boolean(snapshot?.lane === 'execution') &&
    Boolean(planReadySignal?.ready) &&
    !Boolean(planReadySignal?.failed) &&
    Boolean(planReadyDismissKey) &&
    Boolean(hasPlanRevisionItem) &&
    !hasBlockingPendingRequest &&
    !supersededByUserMessage &&
    !dismissedPlanReadyKeys.has(String(planReadyDismissKey))

  const handleDismissPlanReady = useCallback(() => {
    if (!planReadyDismissKey) {
      return
    }
    setDismissedPlanReadyKeys((previous) => {
      const next = new Set(previous)
      next.add(planReadyDismissKey)
      return next
    })
  }, [planReadyDismissKey])

  const handlePlanAction = useCallback(
    async (action: PlanActionV3, planItemId: string, revision: number) => {
      if (!onPlanAction) {
        return
      }
      await onPlanAction(action, planItemId, revision)
    },
    [onPlanAction],
  )

  const renderGroupedEntry = useCallback(
    (entry: ToolGroupEntryV3) => {
      if (entry.kind === 'item') {
        const reasoningMeta =
          entry.item.kind === 'reasoning'
            ? visibleState.reasoningMetaById.get(entry.item.id)
            : undefined
        return (
          <div key={entry.item.id} className={styles.streamEntry}>
            {renderItemRowV3({
              item: entry.item,
              requestMapByRequestId,
              reasoningMeta,
              expandedItemIds,
              onToggleExpanded: toggleExpanded,
              onRequestAutoScroll: requestAutoScroll,
            })}
          </div>
        )
      }

      const isCollapsed = collapsedToolGroupIds.has(entry.group.id)
      const leadTool = entry.group.items.find((item) => item.kind === 'tool')
      const groupTitle =
        (leadTool && normalizeText(leadTool.title)) ||
        (leadTool && normalizeText(leadTool.toolName)) ||
        'Live tool activity'
      const groupCounts = `${entry.group.toolCount} tools${
        entry.group.supportingItemCount
          ? ` - ${entry.group.supportingItemCount} supporting items`
          : ''
      }`

      return (
        <section
          key={entry.group.id}
          className={`${styles.row} ${styles.rowCard}`}
          data-testid={`conversation-v3-tool-group-${entry.group.id}`}
        >
          <div className={styles.rowRail}>
            <div className={styles.groupShell}>
              <div className={styles.groupHeader}>
                <div>
                  <div className={styles.cardEyebrow}>Tool Stream</div>
                  <div className={styles.cardTitle}>{groupTitle}</div>
                  <div className={styles.groupCounts}>{groupCounts}</div>
                </div>
                <button
                  type="button"
                  className={styles.groupToggle}
                  onClick={() => toggleToolGroup(entry.group.id)}
                >
                  {isCollapsed ? 'Expand' : 'Collapse'}
                </button>
              </div>
              {!isCollapsed ? (
                <div className={styles.groupBody}>
                  {entry.group.items.map((item) => {
                    const reasoningMeta =
                      item.kind === 'reasoning'
                        ? visibleState.reasoningMetaById.get(item.id)
                        : undefined
                    return (
                      <div key={item.id} className={styles.streamEntry}>
                        {renderItemRowV3({
                          item,
                          requestMapByRequestId,
                          reasoningMeta,
                          expandedItemIds,
                          onToggleExpanded: toggleExpanded,
                          onRequestAutoScroll: requestAutoScroll,
                        })}
                      </div>
                    )
                  })}
                </div>
              ) : null}
            </div>
          </div>
        </section>
      )
    },
    [
      collapsedToolGroupIds,
      expandedItemIds,
      requestMapByRequestId,
      requestAutoScroll,
      toggleExpanded,
      toggleToolGroup,
      visibleState.reasoningMetaById,
    ],
  )

  return (
    <div
      ref={containerRef}
      className={styles.feed}
      data-testid="messages-v3-feed"
      onScroll={updateAutoScroll}
    >
      {prefix}

      {groupedEntries.length === 0 && pendingRequestCards.length === 0 && !isLoading ? (
        <div className={styles.empty}>No conversation items yet.</div>
      ) : null}

      <div className={styles.streamStack} data-testid="messages-v3-stream-stack">
        {groupedEntries.map(renderGroupedEntry)}
      </div>

      {pendingRequestCards.length > 0 ? (
        <div className={styles.pendingStack} data-testid="messages-v3-pending-stack">
          {pendingRequestCards.map((request) => (
            <PendingUserInputCardV3
              key={`pending-request-${request.requestId}`}
              request={request}
              item={userInputItemByRequestId.get(request.requestId) ?? null}
              onResolve={onResolveUserInput}
            />
          ))}
        </div>
      ) : null}

      {showPlanReadyCard && planReadySignal?.planItemId && planReadySignal.revision != null ? (
        <div className={styles.planReadyZone} data-testid="messages-v3-plan-ready-zone">
          <PlanReadyFollowupCardV3
            planItemId={planReadySignal.planItemId}
            revision={planReadySignal.revision}
            isSending={isSending}
            onDismiss={handleDismissPlanReady}
            onPlanAction={handlePlanAction}
          />
        </div>
      ) : null}

      {snapshot ? (
        <WorkingIndicatorV3
          processingState={snapshot.processingState as ProcessingState}
          activeTurnId={snapshot.activeTurnId}
          lastCompletedAt={lastCompletedAt}
          lastDurationMs={lastDurationMs}
        />
      ) : null}

      {isLoading && groupedEntries.length === 0 ? (
        <div className={styles.empty}>Loading conversation...</div>
      ) : null}

      {suffix ? <div className={styles.feedSuffix}>{suffix}</div> : null}
      <div ref={bottomRef} />
    </div>
  )
}
