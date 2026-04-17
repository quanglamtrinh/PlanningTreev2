import {
  memo,
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import type {
  ConversationItemV3,
  ItemStatus,
  PendingUserInputRequestV3,
  PlanActionV3,
  ProcessingState,
  ThreadSnapshotV3,
  ToolChange,
  ToolItem as ToolItemV2,
  ToolItemV3,
  UserInputAnswerV3,
  UserInputItemV3,
  UserInputQuestionV3,
} from '../../../../api/types'
import { AgentSpinner } from '../../../../components/AgentSpinner'
import { FileChangeToolRow } from '../FileChangeToolRow'
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
import {
  emitPhase10AnchorRestore,
  emitPhase10Fallback,
  emitPhase10ProgressiveBatch,
  emitRowRenderProfile,
  resetMessagesV3ProfilingState,
  type MessagesV3Phase10Mode,
} from './messagesV3ProfilingHooks'
import { useThreadByIdStoreV3 } from '../../state/threadByIdStoreV3'
import {
  buildParseCacheKey,
  PARSE_CACHE_RENDERER_VERSION,
} from './parseCacheContract'
import {
  buildParseArtifactVariantKey,
  readOrComputeParseArtifact,
  resetParseArtifactCache,
  resetParseArtifactCacheForThread,
} from './parseArtifactCache'
import {
  computeTrailingCommandOutput,
  computeTrailingCommandOutputIncremental,
  type CommandOutputTailCache,
} from './commandOutputTail'
import {
  PHASE11_DEFAULT_DEFERRED_TIMEOUT_MS,
  resolveMessagesV3Phase11Mode,
} from './phase11Config'

const SCROLL_THRESHOLD_PX = 120
const MAX_COMMAND_OUTPUT_LINES = 200
const HEAVY_COMMAND_OUTPUT_CHAR_THRESHOLD = 600
const HEAVY_COMMAND_OUTPUT_LINE_THRESHOLD = 12
const HEAVY_DIFF_FILE_COUNT_THRESHOLD = 5
const HEAVY_DIFF_PAYLOAD_CHAR_THRESHOLD = 3000
const HEAVY_GENERIC_OUTPUT_CHAR_THRESHOLD = 2000
const PAYLOAD_PREVIEW_MAX_CHARS = 1200
const PAYLOAD_PREVIEW_MAX_LINES = 60
const VIEW_STATE_PERSIST_DEBOUNCE_MS = 150
const EMPTY_USER_INPUT_ANSWERS: UserInputAnswerV3[] = []
const PHASE10_MODE_ENV_FLAG = 'VITE_PTM_PHASE10_PROGRESSIVE_VIRTUALIZATION_MODE'
const PHASE11_MARKDOWN_DEFERRED_TIMEOUT_MS = PHASE11_DEFAULT_DEFERRED_TIMEOUT_MS
const PHASE10_PROGRESSIVE_THRESHOLD = 250
const PHASE10_VIRTUALIZATION_THRESHOLD = 300
const PHASE10_PROGRESSIVE_INITIAL_CHUNK = 120
const PHASE10_PROGRESSIVE_BASE_BATCH = 40
const PHASE10_VIRTUAL_BOOTSTRAP_COUNT = 40
const PHASE10_PROGRESSIVE_BATCH_MIN_LEVEL1 = 10
const PHASE10_PROGRESSIVE_BATCH_LEVEL2 = 6
const PHASE10_PROGRESSIVE_FRAME_BUDGET_MS = 8
const PHASE10_OVERSCAN_BASE = 8
const PHASE10_OVERSCAN_LEVEL1 = 6
const PHASE10_OVERSCAN_LEVEL2 = 4
const PHASE10_ANCHOR_DRIFT_BREAK_PX = 2
const PHASE10_ANCHOR_RESTORE_TOLERANCE_PX = 0.5

type RenderBudgetDegradeLevel = 0 | 1 | 2

type StreamAnchorSnapshot = {
  entryKey: string
  offsetWithinViewportPx: number
}

type PendingRequestStatus = PendingUserInputRequestV3['status']

function normalizeText(value: string | null | undefined): string {
  return String(value ?? '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .trim()
}

function extractReviewSummaryText(rawText: string): string | null {
  const normalized = normalizeText(rawText)
  if (!normalized.startsWith('{') || !normalized.endsWith('}')) {
    return null
  }
  try {
    const parsed: unknown = JSON.parse(normalized)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null
    }
    const summary = (parsed as { summary?: unknown }).summary
    if (typeof summary !== 'string') {
      return null
    }
    const rendered = normalizeText(summary)
    return rendered || null
  } catch {
    return null
  }
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

function resolveSnapshotThreadRole(snapshot: ThreadSnapshotV3 | null): ThreadSnapshotV3['threadRole'] | null {
  if (!snapshot) {
    return null
  }
  return snapshot.threadRole
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

function isHeavyCommandOutput(item: ToolItemV3): boolean {
  if (item.toolType !== 'commandExecution') {
    return false
  }
  const output = normalizeText(item.outputText)
  if (!output) {
    return false
  }
  const lineCount = output.split('\n').length
  return (
    output.length >= HEAVY_COMMAND_OUTPUT_CHAR_THRESHOLD ||
    lineCount >= HEAVY_COMMAND_OUTPUT_LINE_THRESHOLD
  )
}

function computeFilePayloadChars(files: ToolItemV3['outputFiles']): number {
  let total = 0
  for (const file of files) {
    total += normalizeText(file.summary).length
    total += normalizeText(file.diff ?? null).length
  }
  return total
}

function isHeavyToolItem(item: ToolItemV3): boolean {
  if (item.toolType === 'commandExecution') {
    return isHeavyCommandOutput(item)
  }
  if (item.toolType === 'fileChange') {
    const fileCount = item.outputFiles.length
    const payloadChars =
      normalizeText(item.argumentsText).length +
      normalizeText(item.outputText).length +
      computeFilePayloadChars(item.outputFiles)
    return (
      fileCount >= HEAVY_DIFF_FILE_COUNT_THRESHOLD ||
      payloadChars >= HEAVY_DIFF_PAYLOAD_CHAR_THRESHOLD
    )
  }
  const outputChars = normalizeText(item.outputText).length
  return outputChars >= HEAVY_GENERIC_OUTPUT_CHAR_THRESHOLD
}

function computeDiffPayloadChars(item: Extract<ConversationItemV3, { kind: 'diff' }>): number {
  let total = normalizeText(item.summaryText).length
  for (const change of item.changes) {
    total += normalizeText(change.summary).length
    total += normalizeText(change.diff).length
  }
  for (const file of item.files) {
    total += normalizeText(file.summary).length
    total += normalizeText(file.patchText).length
  }
  return total
}

function isHeavyDiffItem(item: Extract<ConversationItemV3, { kind: 'diff' }>): boolean {
  const fileCount = Math.max(item.changes.length, item.files.length)
  const payloadChars = computeDiffPayloadChars(item)
  return (
    fileCount >= HEAVY_DIFF_FILE_COUNT_THRESHOLD ||
    payloadChars >= HEAVY_DIFF_PAYLOAD_CHAR_THRESHOLD
  )
}

type PayloadPreview = {
  previewText: string
  truncated: boolean
  originalCharCount: number
  originalLineCount: number
}

function buildPayloadPreview(
  value: string | null | undefined,
  maxChars: number = PAYLOAD_PREVIEW_MAX_CHARS,
  maxLines: number = PAYLOAD_PREVIEW_MAX_LINES,
): PayloadPreview {
  const normalized = String(value ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const lineParts = normalized.split('\n')
  const originalLineCount = lineParts.length
  const originalCharCount = normalized.length
  const byLines = lineParts.slice(0, Math.max(1, maxLines)).join('\n')
  const byChars = byLines.slice(0, Math.max(1, maxChars))
  const truncated = byChars.length < originalCharCount || originalLineCount > maxLines
  return {
    previewText: truncated ? `${byChars}\n\n[Preview truncated]` : byChars,
    truncated,
    originalCharCount,
    originalLineCount,
  }
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
      const hasArguments = Boolean(normalizeText(item.argumentsText))
      const hasOutput = Boolean(normalizeText(item.outputText))
      const hasFiles = item.outputFiles.length > 0
      const hasBody = hasArguments || hasOutput || hasFiles
      const shouldAutoExpand =
        item.status === 'in_progress' ||
        (item.toolType !== 'commandExecution' && hasBody && !isHeavyToolItem(item))
      if (!shouldAutoExpand) {
        target.add(id)
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

export function normalizeMessagesV3Phase10Mode(
  value: string | null | undefined,
): MessagesV3Phase10Mode {
  const normalized = String(value ?? '')
    .trim()
    .toLowerCase()
  if (normalized === 'shadow') {
    return 'shadow'
  }
  if (normalized === 'on') {
    return 'on'
  }
  return 'off'
}

function resolveMessagesV3Phase10Mode(
  modeOverride: MessagesV3Phase10Mode | null | undefined,
): MessagesV3Phase10Mode {
  if (modeOverride) {
    return normalizeMessagesV3Phase10Mode(modeOverride)
  }
  const env = import.meta.env as Record<string, unknown>
  return normalizeMessagesV3Phase10Mode(String(env[PHASE10_MODE_ENV_FLAG] ?? 'off'))
}

function getStreamEntryKey(entry: ToolGroupEntryV3 | null | undefined): string {
  if (!entry) {
    return 'stream_entry:missing'
  }
  if (entry.kind === 'item') {
    return `item:${entry.item.id}`
  }
  return `tool_group:${entry.group.id}`
}

function estimateStreamEntrySize(entry: ToolGroupEntryV3): number {
  if (entry.kind === 'toolGroup') {
    return Math.max(260, 110 * entry.group.items.length)
  }
  if (entry.item.kind === 'message') {
    return 220
  }
  if (entry.item.kind === 'reasoning') {
    return 280
  }
  if (entry.item.kind === 'tool' || entry.item.kind === 'diff') {
    return 320
  }
  if (entry.item.kind === 'review' || entry.item.kind === 'explore') {
    return 240
  }
  return 180
}

function effectiveProgressiveBatchSize(level: RenderBudgetDegradeLevel): number {
  if (level === 2) {
    return PHASE10_PROGRESSIVE_BATCH_LEVEL2
  }
  if (level === 1) {
    return Math.max(
      PHASE10_PROGRESSIVE_BATCH_MIN_LEVEL1,
      Math.floor(PHASE10_PROGRESSIVE_BASE_BATCH / 2),
    )
  }
  return PHASE10_PROGRESSIVE_BASE_BATCH
}

function effectiveVirtualOverscan(level: RenderBudgetDegradeLevel): number {
  if (level === 2) {
    return PHASE10_OVERSCAN_LEVEL2
  }
  if (level === 1) {
    return PHASE10_OVERSCAN_LEVEL1
  }
  return PHASE10_OVERSCAN_BASE
}

function captureVisibleAnchor(container: HTMLDivElement): StreamAnchorSnapshot | null {
  const containerTop = container.getBoundingClientRect().top
  const entryNodes = container.querySelectorAll<HTMLElement>('[data-stream-entry-key]')
  let firstEntryKey: string | null = null
  for (const node of entryNodes) {
    if (!firstEntryKey) {
      const fallbackEntryKey = String(node.dataset.streamEntryKey ?? '').trim()
      if (fallbackEntryKey) {
        firstEntryKey = fallbackEntryKey
      }
    }
    const rect = node.getBoundingClientRect()
    if (rect.bottom <= containerTop) {
      continue
    }
    const entryKey = String(node.dataset.streamEntryKey ?? '').trim()
    if (!entryKey) {
      continue
    }
    return {
      entryKey,
      offsetWithinViewportPx: rect.top - containerTop,
    }
  }
  // JSDOM and some hidden-layout states can report zero-sized rects for all rows.
  // Fall back to the first rendered entry so anchor checks still have a stable key.
  if (firstEntryKey) {
    return {
      entryKey: firstEntryKey,
      offsetWithinViewportPx: 0,
    }
  }
  return null
}

function findStreamEntryNode(container: HTMLDivElement, entryKey: string): HTMLElement | null {
  const entryNodes = container.querySelectorAll<HTMLElement>('[data-stream-entry-key]')
  for (const node of entryNodes) {
    if (String(node.dataset.streamEntryKey ?? '') === entryKey) {
      return node
    }
  }
  return null
}

function commandRanLabel(status: ItemStatus): string {
  return status === 'in_progress' ? 'Running' : 'Ran'
}

function normalizeDiffKind(
  value: string | null | undefined,
  fallback: ToolChange['kind'] = 'modify',
): ToolChange['kind'] {
  const normalized = String(value ?? '').trim().toLowerCase()
  if (normalized === 'add' || normalized === 'create' || normalized === 'created' || normalized === 'new') {
    return 'add'
  }
  if (
    normalized === 'delete' ||
    normalized === 'deleted' ||
    normalized === 'remove' ||
    normalized === 'removed'
  ) {
    return 'delete'
  }
  if (
    normalized === 'modify' ||
    normalized === 'modified' ||
    normalized === 'update' ||
    normalized === 'updated' ||
    normalized === 'change' ||
    normalized === 'changed'
  ) {
    return 'modify'
  }
  return fallback
}

function changeTypeToDiffKind(changeType: 'created' | 'updated' | 'deleted'): ToolChange['kind'] {
  if (changeType === 'created') {
    return 'add'
  }
  if (changeType === 'deleted') {
    return 'delete'
  }
  return 'modify'
}

function diffKindToChangeType(kind: ToolChange['kind']): 'created' | 'updated' | 'deleted' {
  if (kind === 'add') {
    return 'created'
  }
  if (kind === 'delete') {
    return 'deleted'
  }
  return 'updated'
}

function normalizeDiffText(value: string | null | undefined): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const trimmed = value.trim()
  return trimmed ? trimmed : null
}

function toolChangesFromOutputFiles(files: ToolItemV3['outputFiles']): ToolChange[] {
  return files
    .map((file) => {
      const path = normalizeText(file.path)
      if (!path) {
        return null
      }
      const kind = normalizeDiffKind(file.kind, changeTypeToDiffKind(file.changeType))
      return {
        path,
        kind,
        diff: normalizeDiffText(file.diff),
        summary: file.summary ?? null,
      }
    })
    .filter((change): change is ToolChange => change !== null)
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
  dismissedPlanReadyKeys: Set<string>,
): MessagesV3ViewState {
  return {
    schemaVersion: 1,
    expandedItemIds: [...expandedItemIds],
    collapsedToolGroupIds: [],
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

function emitRowRenderProfileForItem(item: ConversationItemV3): void {
  emitRowRenderProfile({
    threadId: item.threadId,
    itemId: item.id,
    kind: item.kind,
    status: item.status,
    updatedAt: item.updatedAt,
    sequence: item.sequence,
  })
  useThreadByIdStoreV3.getState().recordStreamingRowRender(item.kind === 'message' && item.status === 'in_progress')
}

function sameRenderableItemVersion(
  prev: Pick<ConversationItemV3, 'id' | 'kind' | 'threadId' | 'sequence' | 'status' | 'updatedAt'>,
  next: Pick<ConversationItemV3, 'id' | 'kind' | 'threadId' | 'sequence' | 'status' | 'updatedAt'>,
): boolean {
  return (
    prev.id === next.id &&
    prev.kind === next.kind &&
    prev.threadId === next.threadId &&
    prev.sequence === next.sequence &&
    prev.status === next.status &&
    prev.updatedAt === next.updatedAt
  )
}

function IconCommandLineChevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`${styles.commandChevron} ${expanded ? styles.commandChevronExpanded : ''}`}
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M6 9l6 6 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
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
  itemUpdatedAt,
  outputText,
  onRequestAutoScroll,
}: {
  itemId: string
  itemUpdatedAt: string
  outputText: string
  onRequestAutoScroll?: () => void
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const pinnedRef = useRef(true)
  const [, setPinnedVersion] = useState(0)
  const incrementalTailRef = useRef<CommandOutputTailCache | null>(null)
  const phase11Mode = resolveMessagesV3Phase11Mode(null)

  const visibleOutput = useMemo(() => {
    const itemKey = `command_output:${itemId}:${itemUpdatedAt}`
    const baseline = computeTrailingCommandOutput(outputText, MAX_COMMAND_OUTPUT_LINES)
    if (phase11Mode === 'off') {
      return baseline
    }
    const incremental = computeTrailingCommandOutputIncremental({
      previous: incrementalTailRef.current,
      itemKey,
      outputText,
      maxLines: MAX_COMMAND_OUTPUT_LINES,
    })
    incrementalTailRef.current = incremental.cache
    if (phase11Mode === 'shadow') {
      return baseline
    }
    return incremental.visibleOutput
  }, [itemId, itemUpdatedAt, outputText, phase11Mode])

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

function MessageRowV3({
  item,
  streamingTextOverride,
}: {
  item: Extract<ConversationItemV3, { kind: 'message' }>
  streamingTextOverride?: string | null
}) {
  emitRowRenderProfileForItem(item)
  const phase11Mode = resolveMessagesV3Phase11Mode(null)

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
  const messageSourceText = streamingTextOverride ?? item.text
  const streamOverlayToken =
    streamingTextOverride == null
      ? null
      : `${streamingTextOverride.length}:${streamingTextOverride.slice(-32)}`
  const messageRenderUpdatedAt =
    streamOverlayToken == null ? item.updatedAt : `${item.updatedAt}:${streamOverlayToken}`
  const messageParseKey = buildParseCacheKey({
    threadId: item.threadId,
    itemId: item.id,
    updatedAt: messageRenderUpdatedAt,
    mode: 'message_markdown',
    rendererVersion: PARSE_CACHE_RENDERER_VERSION,
  })
  const renderedText = readOrComputeParseArtifact<string>(
    buildParseArtifactVariantKey(messageParseKey, 'rendered_message_text'),
    () =>
      item.role === 'assistant'
        ? extractReviewSummaryText(messageSourceText) ?? messageSourceText
        : messageSourceText,
  ).value

  return (
    <article className={`${styles.row} ${roleClass}`} data-testid="conversation-v3-item-message">
      <div className={styles.rowRail}>
        <div
          className={`${styles.messageShell} ${item.role === 'user' ? styles.messageShellUser : styles.messageShellAssistant}`}
        >
          <div className={`${styles.messageBubble} ${bubbleClass}`}>
            <ConversationMarkdown
              content={renderedText}
              phase11Mode={phase11Mode}
              phase11DeferredTimeoutMs={PHASE11_MARKDOWN_DEFERRED_TIMEOUT_MS}
              parseTrace={{
                threadId: item.threadId,
                itemId: item.id,
                updatedAt: messageRenderUpdatedAt,
                mode: 'message_markdown',
                source: 'messages_v3.message_row',
              }}
            />
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
  emitRowRenderProfileForItem(item)

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
  onOpenFullArtifact,
}: {
  item: Extract<ConversationItemV3, { kind: 'tool' }>
  isExpanded: boolean
  onToggle: (itemId: string) => void
  onRequestAutoScroll?: () => void
  onOpenFullArtifact: (title: string, content: string) => void
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
  const outputPreview = useMemo(() => buildPayloadPreview(item.outputText), [item.outputText])

  const commandBar =
    hasBody && !showBody ? (
      <div className={`${styles.commandLineBar} ${styles.commandLineBarCollapsed}`}>
        <div className={styles.commandLineBarTop}>
          <span className={styles.commandRanLabel}>{ranLabel}</span>
          <span className={styles.commandLineTextCollapsed}>{headline}</span>
          <span className={styles.commandChevronSlot}>
            <IconCommandLineChevron expanded={false} />
          </span>
        </div>
      </div>
    ) : hasBody && showBody ? (
      <div className={`${styles.commandLineBar} ${styles.commandLineBarExpanded}`}>
        <div className={styles.commandLineBarTop}>
          <span className={styles.commandRanLabel}>{ranLabel}</span>
          <span className={styles.commandChevronSlot}>
            <IconCommandLineChevron expanded />
          </span>
        </div>
        <span className={styles.commandLineTextExpanded}>{headline}</span>
      </div>
    ) : (
      <div className={`${styles.commandLineBar} ${styles.commandLineBarExpanded}`}>
        <div className={styles.commandLineBarTop}>
          <span className={styles.commandRanLabel}>{ranLabel}</span>
        </div>
        <span className={styles.commandLineTextExpanded}>{headline}</span>
      </div>
    )

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-tool">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection} ${styles.commandCard}`}>
          <div className={styles.terminalZone}>
            {hasBody ? (
              <button
                type="button"
                className={styles.commandLineBarButton}
                onClick={() => onToggle(item.id)}
                aria-expanded={showBody}
                aria-label={showBody ? 'Collapse command details' : 'Expand command details'}
                title={headline}
              >
                {commandBar}
              </button>
            ) : (
              commandBar
            )}

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
                  <>
                    <CommandOutputViewportV3
                      itemId={item.id}
                      itemUpdatedAt={item.updatedAt}
                      outputText={outputPreview.truncated ? outputPreview.previewText : item.outputText}
                      onRequestAutoScroll={onRequestAutoScroll}
                    />
                    {outputPreview.truncated ? (
                      <div className={styles.actionRow}>
                        <button
                          type="button"
                          className={styles.secondaryButton}
                          onClick={() =>
                            onOpenFullArtifact(
                              `Command output (${outputPreview.originalLineCount} lines)`,
                              item.outputText,
                            )
                          }
                        >
                          View full output
                        </button>
                      </div>
                    ) : null}
                  </>
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
  onOpenFullArtifact,
}: {
  item: Extract<ConversationItemV3, { kind: 'tool' }>
  isExpanded: boolean
  onToggle: (itemId: string) => void
  onRequestAutoScroll?: () => void
  onOpenFullArtifact: (title: string, content: string) => void
}) {
  emitRowRenderProfileForItem(item)

  const effectiveChanges = useMemo(() => toolChangesFromOutputFiles(item.outputFiles), [item.outputFiles])
  const fileChangeItem = useMemo<ToolItemV2 | null>(() => {
    if (item.toolType !== 'fileChange') {
      return null
    }
    return {
      ...item,
      kind: 'tool',
      toolType: 'fileChange',
      outputFiles: item.outputFiles.map((file) => ({
        path: file.path,
        changeType: file.changeType,
        summary: file.summary,
        kind: normalizeDiffKind(file.kind, changeTypeToDiffKind(file.changeType)),
        diff: normalizeDiffText(file.diff),
      })),
      changes: effectiveChanges,
    }
  }, [effectiveChanges, item])

  if (item.toolType === 'fileChange') {
    return (
      <FileChangeToolRow
        item={fileChangeItem as ToolItemV2}
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
        onOpenFullArtifact={onOpenFullArtifact}
      />
    )
  }

  const headline = normalizeText(item.title) || normalizeText(item.toolName) || 'Tool activity'
  const hasArguments = Boolean(normalizeText(item.argumentsText))
  const hasOutput = Boolean(normalizeText(item.outputText))
  const hasFiles = item.outputFiles.length > 0
  const hasBody = hasArguments || hasOutput || hasFiles
  const showBody = !hasBody || isExpanded
  const outputPreview = useMemo(() => buildPayloadPreview(item.outputText), [item.outputText])

  const toolBar = (
    <div
      className={`${styles.commandLineBar} ${
        showBody ? styles.commandLineBarExpanded : styles.commandLineBarCollapsed
      }`}
    >
      {showBody ? (
        <>
          <div className={styles.commandLineBarTop}>
            <span className={styles.commandCardEyebrow}>Tool</span>
            <span className={`${styles.statusPill} ${toStatusClassName(item.status)}`}>
              {item.status}
            </span>
            {item.toolName ? <span className={styles.toolLineMeta}>{item.toolName}</span> : null}
            {item.exitCode != null ? (
              <span className={styles.toolLineMeta}>exit {item.exitCode}</span>
            ) : null}
            {hasBody ? (
              <span className={styles.commandChevronSlot}>
                <IconCommandLineChevron expanded />
              </span>
            ) : null}
          </div>
          <span className={styles.commandLineTextExpanded}>{headline}</span>
        </>
      ) : (
        <div className={styles.commandLineBarTop}>
          <span className={styles.commandCardEyebrow}>Tool</span>
          <span className={`${styles.statusPill} ${toStatusClassName(item.status)}`}>{item.status}</span>
          {item.toolName ? <span className={styles.toolLineMeta}>{item.toolName}</span> : null}
          {item.exitCode != null ? (
            <span className={styles.toolLineMeta}>exit {item.exitCode}</span>
          ) : null}
          <span className={styles.commandLineTextCollapsed}>{headline}</span>
          {hasBody ? (
            <span className={styles.commandChevronSlot}>
              <IconCommandLineChevron expanded={false} />
            </span>
          ) : null}
        </div>
      )}
    </div>
  )

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-tool">
      <div className={styles.rowRail}>
        <div className={`${styles.card} ${styles.cardSection}`}>
          <div className={styles.terminalZone}>
            {hasBody ? (
              <button
                type="button"
                className={styles.commandLineBarButton}
                onClick={() => onToggle(item.id)}
                aria-expanded={showBody}
                aria-label={showBody ? 'Collapse tool details' : 'Expand tool details'}
              >
                {toolBar}
              </button>
            ) : (
              toolBar
            )}
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
              <pre className={styles.plainPre}>
                {outputPreview.truncated ? outputPreview.previewText : item.outputText}
              </pre>
              {outputPreview.truncated ? (
                <div className={styles.actionRow}>
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    onClick={() =>
                      onOpenFullArtifact(
                        `Tool output (${outputPreview.originalLineCount} lines)`,
                        item.outputText,
                      )
                    }
                  >
                    View full output
                  </button>
                </div>
              ) : null}
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

function diffItemV3ToSyntheticFileChangeTool(item: Extract<ConversationItemV3, { kind: 'diff' }>): ToolItemV2 {
  const canonicalChanges: ToolChange[] =
    item.changes.length > 0
      ? item.changes
          .map((change) => {
            const path = normalizeText(change.path)
            if (!path) {
              return null
            }
            const kind = normalizeDiffKind(change.kind, 'modify')
            return {
              path,
              kind,
              diff: normalizeDiffText(change.diff),
              summary: change.summary ?? null,
            }
          })
          .filter((change): change is ToolChange => change !== null)
      : item.files
          .map((file) => {
            const path = normalizeText(file.path)
            if (!path) {
              return null
            }
            const kind = changeTypeToDiffKind(file.changeType)
            return {
              path,
              kind,
              diff: normalizeDiffText(file.patchText),
              summary: file.summary ?? null,
            }
          })
          .filter((change): change is ToolChange => change !== null)

  const outputFiles = canonicalChanges.map((change) => ({
    path: change.path,
    changeType: diffKindToChangeType(change.kind),
    summary: change.summary,
    kind: change.kind,
    diff: change.diff,
  }))
  const outputText = canonicalChanges
    .map((change) => normalizeDiffText(change.diff))
    .filter((diff): diff is string => Boolean(diff))
    .join('\n\n')
  return {
    id: item.id,
    kind: 'tool',
    threadId: item.threadId,
    turnId: item.turnId,
    sequence: item.sequence,
    createdAt: item.createdAt,
    updatedAt: item.updatedAt,
    status: item.status,
    source: item.source,
    tone: item.tone,
    metadata: item.metadata,
    toolType: 'fileChange',
    title: item.title ?? 'File changes',
    toolName: null,
    callId: null,
    argumentsText: item.summaryText,
    outputText,
    outputFiles,
    changes: canonicalChanges,
    exitCode: null,
  }
}

function metadataTextValue(item: Extract<ConversationItemV3, { kind: 'diff' }>, key: string): string {
  const value = item.metadata?.[key]
  return String(value ?? '').trim().toLowerCase()
}

function isFileChangeSemanticDiff(item: Extract<ConversationItemV3, { kind: 'diff' }>): boolean {
  const semanticKind = metadataTextValue(item, 'semanticKind')
  if (semanticKind) {
    return semanticKind === 'filechange'
  }
  const v2Kind = metadataTextValue(item, 'v2Kind')
  if (v2Kind) {
    return v2Kind === 'tool'
  }
  return false
}

function ReviewRowV3({ item }: { item: Extract<ConversationItemV3, { kind: 'review' }> }) {
  emitRowRenderProfileForItem(item)
  const phase11Mode = resolveMessagesV3Phase11Mode(null)

  const reviewParseKey = buildParseCacheKey({
    threadId: item.threadId,
    itemId: item.id,
    updatedAt: item.updatedAt,
    mode: 'message_markdown',
    rendererVersion: PARSE_CACHE_RENDERER_VERSION,
  })
  const renderedText = readOrComputeParseArtifact<string>(
    buildParseArtifactVariantKey(reviewParseKey, 'rendered_review_text'),
    () => extractReviewSummaryText(item.text) ?? item.text,
  ).value
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
          <ConversationMarkdown
            content={renderedText}
            phase11Mode={phase11Mode}
            phase11DeferredTimeoutMs={PHASE11_MARKDOWN_DEFERRED_TIMEOUT_MS}
            parseTrace={{
              threadId: item.threadId,
              itemId: item.id,
              updatedAt: item.updatedAt,
              mode: 'message_markdown',
              source: 'messages_v3.review_row',
            }}
          />
        </div>
      </div>
    </article>
  )
}

function ExploreRowV3({ item }: { item: Extract<ConversationItemV3, { kind: 'explore' }> }) {
  emitRowRenderProfileForItem(item)
  const phase11Mode = resolveMessagesV3Phase11Mode(null)

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
          <ConversationMarkdown
            content={item.text}
            phase11Mode={phase11Mode}
            phase11DeferredTimeoutMs={PHASE11_MARKDOWN_DEFERRED_TIMEOUT_MS}
            parseTrace={{
              threadId: item.threadId,
              itemId: item.id,
              updatedAt: item.updatedAt,
              mode: 'message_markdown',
              source: 'messages_v3.explore_row',
            }}
          />
        </div>
      </div>
    </article>
  )
}

function DiffRowV3({
  item,
  isExpanded,
  onToggle,
  onOpenFullArtifact,
}: {
  item: Extract<ConversationItemV3, { kind: 'diff' }>
  isExpanded: boolean
  onToggle: (itemId: string) => void
  onOpenFullArtifact: (title: string, content: string) => void
}) {
  emitRowRenderProfileForItem(item)

  const syntheticFileChangeItem = useMemo<ToolItemV2 | null>(() => {
    if (!isFileChangeSemanticDiff(item)) {
      return null
    }
    return diffItemV3ToSyntheticFileChangeTool(item)
  }, [item])

  if (isFileChangeSemanticDiff(item)) {
    return (
      <FileChangeToolRow
        item={syntheticFileChangeItem as ToolItemV2}
        isExpanded={isExpanded}
        onToggle={onToggle}
        dataTestId="conversation-v3-item-diff"
      />
    )
  }

  const hasBody = Boolean(item.summaryText) || item.files.length > 0
  const heavy = isHeavyDiffItem(item)
  const showBody = !hasBody || !heavy || item.status === 'in_progress' || isExpanded
  const summaryPreview = useMemo(() => buildPayloadPreview(item.summaryText), [item.summaryText])

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

          {hasBody && heavy ? (
            <button
              type="button"
              className={styles.commandLineBarButton}
              onClick={() => onToggle(item.id)}
              aria-expanded={showBody}
              aria-label={showBody ? 'Collapse diff details' : 'Expand diff details'}
            >
              <div
                className={`${styles.commandLineBar} ${
                  showBody ? styles.commandLineBarExpanded : styles.commandLineBarCollapsed
                }`}
              >
                <div className={styles.commandLineBarTop}>
                  <span className={styles.commandCardEyebrow}>Diff</span>
                  <span className={styles.commandLineTextCollapsed}>
                    {item.files.length > 0 ? `${item.files.length} files` : 'Large diff payload'}
                  </span>
                  <span className={styles.commandChevronSlot}>
                    <IconCommandLineChevron expanded={showBody} />
                  </span>
                </div>
              </div>
            </button>
          ) : null}

          {showBody && item.summaryText ? (
            <div className={styles.section}>
              <div className={styles.sectionTitle}>Summary</div>
              <div className={styles.subtleText}>
                {summaryPreview.truncated ? summaryPreview.previewText : item.summaryText}
              </div>
              {summaryPreview.truncated ? (
                <div className={styles.actionRow}>
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    onClick={() =>
                      onOpenFullArtifact(
                        `Diff summary (${summaryPreview.originalLineCount} lines)`,
                        item.summaryText ?? '',
                      )
                    }
                  >
                    View full summary
                  </button>
                </div>
              ) : null}
            </div>
          ) : null}

          {showBody && item.files.length ? (
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
  emitRowRenderProfileForItem(item)

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
  emitRowRenderProfileForItem(item)

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
  emitRowRenderProfileForItem(item)

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

type MessageRowProps = { item: Extract<ConversationItemV3, { kind: 'message' }> }
type ReasoningRowProps = {
  item: Extract<ConversationItemV3, { kind: 'reasoning' }>
  meta?: ReasoningPresentationMetaV3
  isExpanded: boolean
  onToggle: (itemId: string) => void
}
type ToolRowProps = {
  item: Extract<ConversationItemV3, { kind: 'tool' }>
  isExpanded: boolean
  onToggle: (itemId: string) => void
  onRequestAutoScroll?: () => void
  onOpenFullArtifact: (title: string, content: string) => void
}
type ReviewRowProps = { item: Extract<ConversationItemV3, { kind: 'review' }> }
type ExploreRowProps = { item: Extract<ConversationItemV3, { kind: 'explore' }> }
type DiffRowProps = {
  item: Extract<ConversationItemV3, { kind: 'diff' }>
  isExpanded: boolean
  onToggle: (itemId: string) => void
  onOpenFullArtifact: (title: string, content: string) => void
}
type StatusRowProps = { item: Extract<ConversationItemV3, { kind: 'status' }> }
type ErrorRowProps = { item: Extract<ConversationItemV3, { kind: 'error' }> }
type UserInputInlineRowProps = {
  item: Extract<ConversationItemV3, { kind: 'userInput' }>
  status: PendingRequestStatus
  answers: UserInputAnswerV3[]
}

function areMessageRowPropsEqual(prev: MessageRowProps, next: MessageRowProps): boolean {
  return (
    sameRenderableItemVersion(prev.item, next.item) &&
    prev.item.role === next.item.role &&
    prev.item.text === next.item.text &&
    prev.item.format === next.item.format
  )
}

function areReasoningRowPropsEqual(prev: ReasoningRowProps, next: ReasoningRowProps): boolean {
  return (
    sameRenderableItemVersion(prev.item, next.item) &&
    prev.isExpanded === next.isExpanded &&
    prev.onToggle === next.onToggle &&
    prev.meta?.hasBody === next.meta?.hasBody &&
    prev.meta?.visibleSummary === next.meta?.visibleSummary &&
    prev.meta?.visibleDetail === next.meta?.visibleDetail &&
    prev.meta?.workingLabel === next.meta?.workingLabel
  )
}

function areToolRowPropsEqual(prev: ToolRowProps, next: ToolRowProps): boolean {
  return (
    sameRenderableItemVersion(prev.item, next.item) &&
    prev.isExpanded === next.isExpanded &&
    prev.onToggle === next.onToggle &&
    prev.onRequestAutoScroll === next.onRequestAutoScroll &&
    prev.onOpenFullArtifact === next.onOpenFullArtifact &&
    prev.item.toolType === next.item.toolType
  )
}

function areReviewRowPropsEqual(prev: ReviewRowProps, next: ReviewRowProps): boolean {
  return (
    sameRenderableItemVersion(prev.item, next.item) &&
    prev.item.title === next.item.title &&
    prev.item.text === next.item.text &&
    prev.item.disposition === next.item.disposition
  )
}

function areExploreRowPropsEqual(prev: ExploreRowProps, next: ExploreRowProps): boolean {
  return (
    sameRenderableItemVersion(prev.item, next.item) &&
    prev.item.title === next.item.title &&
    prev.item.text === next.item.text
  )
}

function areDiffRowPropsEqual(prev: DiffRowProps, next: DiffRowProps): boolean {
  return (
    sameRenderableItemVersion(prev.item, next.item) &&
    prev.isExpanded === next.isExpanded &&
    prev.onToggle === next.onToggle &&
    prev.onOpenFullArtifact === next.onOpenFullArtifact
  )
}

function areStatusRowPropsEqual(prev: StatusRowProps, next: StatusRowProps): boolean {
  return (
    sameRenderableItemVersion(prev.item, next.item) &&
    prev.item.code === next.item.code &&
    prev.item.label === next.item.label &&
    prev.item.detail === next.item.detail
  )
}

function areErrorRowPropsEqual(prev: ErrorRowProps, next: ErrorRowProps): boolean {
  return (
    sameRenderableItemVersion(prev.item, next.item) &&
    prev.item.code === next.item.code &&
    prev.item.title === next.item.title &&
    prev.item.message === next.item.message
  )
}

function areUserInputInlineRowPropsEqual(
  prev: UserInputInlineRowProps,
  next: UserInputInlineRowProps,
): boolean {
  return (
    sameRenderableItemVersion(prev.item, next.item) &&
    prev.status === next.status &&
    prev.answers === next.answers
  )
}

const MemoMessageRowV3 = memo(MessageRowV3, areMessageRowPropsEqual)
const MemoReasoningRowV3 = memo(ReasoningRowV3, areReasoningRowPropsEqual)
const MemoToolRowV3 = memo(ToolRowV3, areToolRowPropsEqual)
const MemoReviewRowV3 = memo(ReviewRowV3, areReviewRowPropsEqual)
const MemoExploreRowV3 = memo(ExploreRowV3, areExploreRowPropsEqual)
const MemoDiffRowV3 = memo(DiffRowV3, areDiffRowPropsEqual)
const MemoStatusRowV3 = memo(StatusRowV3, areStatusRowPropsEqual)
const MemoErrorRowV3 = memo(ErrorRowV3, areErrorRowPropsEqual)
const MemoUserInputInlineRowV3 = memo(UserInputInlineRowV3, areUserInputInlineRowPropsEqual)

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
  onOpenFullArtifact,
  streamingTextLaneByItemId,
}: {
  item: ConversationItemV3
  requestMapByRequestId: Map<string, PendingUserInputRequestV3>
  reasoningMeta?: ReasoningPresentationMetaV3
  expandedItemIds: Set<string>
  onToggleExpanded: (itemId: string) => void
  onRequestAutoScroll: () => void
  onOpenFullArtifact: (title: string, content: string) => void
  streamingTextLaneByItemId: Map<string, string>
}) {
  const isExpanded = expandedItemIds.has(item.id)

  if (item.kind === 'message') {
    return (
      <MemoMessageRowV3
        item={item}
        streamingTextOverride={streamingTextLaneByItemId.get(item.id) ?? null}
      />
    )
  }
  if (item.kind === 'reasoning') {
    return (
      <MemoReasoningRowV3
        item={item}
        meta={reasoningMeta}
        isExpanded={isExpanded}
        onToggle={onToggleExpanded}
      />
    )
  }
  if (item.kind === 'tool') {
    return (
      <MemoToolRowV3
        item={item}
        isExpanded={isExpanded}
        onToggle={onToggleExpanded}
        onRequestAutoScroll={onRequestAutoScroll}
        onOpenFullArtifact={onOpenFullArtifact}
      />
    )
  }
  if (item.kind === 'review') {
    return <MemoReviewRowV3 item={item} />
  }
  if (item.kind === 'diff') {
    return (
      <MemoDiffRowV3
        item={item}
        isExpanded={isExpanded}
        onToggle={onToggleExpanded}
        onOpenFullArtifact={onOpenFullArtifact}
      />
    )
  }
  if (item.kind === 'explore') {
    return <MemoExploreRowV3 item={item} />
  }
  if (item.kind === 'status') {
    return <MemoStatusRowV3 item={item} />
  }
  if (item.kind === 'error') {
    return <MemoErrorRowV3 item={item} />
  }
  if (item.kind === 'userInput') {
    const request = requestMapByRequestId.get(item.requestId)
    const status = request?.status ?? effectiveUserInputStatus(item, requestMapByRequestId)
    const answers = request?.answers.length ? request.answers : item.answers
    return <MemoUserInputInlineRowV3 item={item} status={status} answers={answers} />
  }
  return null
}

export function MessagesV3({
  snapshot,
  isLoading,
  isSending = false,
  hasOlderHistory = false,
  isLoadingHistory = false,
  onLoadMoreHistory,
  prefix,
  suffix,
  onResolveUserInput,
  onPlanAction,
  lastCompletedAt,
  lastDurationMs,
  threadChatFlatCanvas = false,
  phase10ModeOverride = null,
}: {
  snapshot: ThreadSnapshotV3 | null
  isLoading: boolean
  isSending?: boolean
  hasOlderHistory?: boolean
  isLoadingHistory?: boolean
  onLoadMoreHistory?: () => void
  prefix?: ReactNode
  suffix?: ReactNode
  /** Breadcrumb thread: one #fcf9f7 canvas (no gray “cards” in the scroll area). */
  threadChatFlatCanvas?: boolean
  onResolveUserInput: (requestId: string, answers: UserInputAnswerV3[]) => Promise<void> | void
  onPlanAction?: (
    action: PlanActionV3,
    planItemId: string,
    revision: number,
  ) => Promise<void> | void
  lastCompletedAt?: number | null
  lastDurationMs?: number | null
  phase10ModeOverride?: MessagesV3Phase10Mode | null
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const autoScrollRef = useRef(true)
  const manuallyToggledExpandedRef = useRef<Set<string>>(new Set())
  const previousThreadIdRef = useRef<string | null>(null)
  const snapshotRef = useRef(snapshot)
  snapshotRef.current = snapshot

  const [expandedItemIds, setExpandedItemIds] = useState<Set<string>>(new Set())
  const [dismissedPlanReadyKeys, setDismissedPlanReadyKeys] = useState<Set<string>>(new Set())
  const [progressiveVisibleCount, setProgressiveVisibleCount] = useState(0)
  const [budgetDegradeLevel, setBudgetDegradeLevel] = useState<RenderBudgetDegradeLevel>(0)
  const [phase10FallbackVersion, setPhase10FallbackVersion] = useState(0)
  const [deferNonCriticalDecorations, setDeferNonCriticalDecorations] = useState(false)
  const [fullArtifactView, setFullArtifactView] = useState<{ title: string; content: string } | null>(null)
  const fallbackReasonsByThreadRef = useRef<Map<string, string>>(new Map())
  const anchorSnapshotRef = useRef<StreamAnchorSnapshot | null>(null)
  const previousThreadForProgressiveRef = useRef<string | null>(null)
  const previousFrameTsRef = useRef<number | null>(null)
  const consecutiveFramesOver16Ref = useRef(0)
  const consecutiveFramesOver24Ref = useRef(0)
  const stableFrameCountRef = useRef(0)

  const threadId = snapshot?.threadId ?? null
  const phase10Mode = resolveMessagesV3Phase10Mode(phase10ModeOverride)
  const threadFallbackReason = useMemo(() => {
    if (!threadId) {
      return null
    }
    return fallbackReasonsByThreadRef.current.get(threadId) ?? null
  }, [phase10FallbackVersion, threadId])
  const threadFallbackActive = threadFallbackReason != null
  const pendingRequests = snapshot?.uiSignals.activeUserInputRequests ?? []
  const requestMapByRequestId = useMemo(() => requestByRequestId(pendingRequests), [pendingRequests])
  const streamingTextLane = useThreadByIdStoreV3((state) => state.streamingTextLane)
  const streamingTextLaneByItemId = useMemo(() => {
    const map = new Map<string, string>()
    if (!threadId) {
      return map
    }
    for (const item of snapshot?.items ?? []) {
      if (item.kind !== 'message' || item.role !== 'assistant' || item.status !== 'in_progress') {
        continue
      }
      const lane = streamingTextLane[`${threadId}::${item.id}`]
      if (lane?.text) {
        map.set(item.id, lane.text)
      }
    }
    return map
  }, [snapshot?.items, streamingTextLane, threadId])

  useEffect(() => {
    resetMessagesV3ProfilingState()
    const previousThreadId = previousThreadIdRef.current
    if (previousThreadId && previousThreadId !== threadId) {
      resetParseArtifactCacheForThread(previousThreadId)
    }
    if (threadId == null) {
      resetParseArtifactCache()
    }
    anchorSnapshotRef.current = null
    previousThreadForProgressiveRef.current = null
    previousFrameTsRef.current = null
    consecutiveFramesOver16Ref.current = 0
    consecutiveFramesOver24Ref.current = 0
    stableFrameCountRef.current = 0
    setBudgetDegradeLevel(0)
    setDeferNonCriticalDecorations(false)
    setFullArtifactView(null)
    previousThreadIdRef.current = threadId
  }, [threadId])

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
  const phase10ComputationEnabled =
    phase10Mode !== 'off' &&
    !threadFallbackActive &&
    groupedEntries.length >= PHASE10_PROGRESSIVE_THRESHOLD
  const phase10ProgressiveRenderEnabled =
    phase10Mode === 'on' &&
    !threadFallbackActive &&
    groupedEntries.length >= PHASE10_PROGRESSIVE_THRESHOLD
  const phase10VirtualizationEnabled =
    phase10Mode === 'on' &&
    !threadFallbackActive &&
    groupedEntries.length >= PHASE10_VIRTUALIZATION_THRESHOLD

  const activatePhase10Fallback = useCallback(
    (
      reason:
        | 'anchor_missing'
        | 'anchor_drift'
        | 'virtualization_anchor_missing'
        | 'virtualization_anchor_drift',
      details?: { entryKey?: string | null; driftPx?: number | null },
    ) => {
      if (!threadId || phase10Mode !== 'on') {
        return
      }
      const existingReason = fallbackReasonsByThreadRef.current.get(threadId)
      if (existingReason) {
        return
      }
      fallbackReasonsByThreadRef.current.set(threadId, reason)
      setPhase10FallbackVersion((previous) => previous + 1)
      setProgressiveVisibleCount(groupedEntries.length)
      setBudgetDegradeLevel(0)
      setDeferNonCriticalDecorations(false)
      emitPhase10Fallback({
        threadId,
        mode: phase10Mode,
        reason,
        entryKey: details?.entryKey ?? null,
        driftPx: details?.driftPx ?? null,
      })
    },
    [groupedEntries.length, phase10Mode, threadId],
  )

  useEffect(() => {
    const entryCount = groupedEntries.length
    const isThreadChanged = previousThreadForProgressiveRef.current !== threadId
    previousThreadForProgressiveRef.current = threadId
    if (!phase10ComputationEnabled) {
      setProgressiveVisibleCount(entryCount)
      return
    }
    const initialCount = Math.min(PHASE10_PROGRESSIVE_INITIAL_CHUNK, entryCount)
    if (isThreadChanged) {
      setProgressiveVisibleCount(initialCount)
      return
    }
    setProgressiveVisibleCount((previous) => {
      if (previous <= 0) {
        return initialCount
      }
      if (previous > entryCount) {
        return entryCount
      }
      return previous
    })
  }, [groupedEntries.length, phase10ComputationEnabled, threadId])

  useEffect(() => {
    if (!phase10ComputationEnabled) {
      previousFrameTsRef.current = null
      consecutiveFramesOver16Ref.current = 0
      consecutiveFramesOver24Ref.current = 0
      stableFrameCountRef.current = 0
      setBudgetDegradeLevel(0)
      setDeferNonCriticalDecorations(false)
      return
    }
    let rafId = 0
    let cancelled = false
    const onFrame = (timestamp: number) => {
      if (cancelled) {
        return
      }
      const previousTs = previousFrameTsRef.current
      previousFrameTsRef.current = timestamp
      if (previousTs != null) {
        const frameDurationMs = Math.max(0, timestamp - previousTs)
        if (frameDurationMs > 24) {
          consecutiveFramesOver24Ref.current += 1
          consecutiveFramesOver16Ref.current += 1
          stableFrameCountRef.current = 0
        } else if (frameDurationMs > 16) {
          consecutiveFramesOver24Ref.current = 0
          consecutiveFramesOver16Ref.current += 1
          stableFrameCountRef.current = 0
        } else if (frameDurationMs <= 12) {
          consecutiveFramesOver24Ref.current = 0
          consecutiveFramesOver16Ref.current = 0
          stableFrameCountRef.current += 1
        } else {
          consecutiveFramesOver24Ref.current = 0
          consecutiveFramesOver16Ref.current = 0
          stableFrameCountRef.current = 0
        }

        setBudgetDegradeLevel((previousLevel) => {
          let nextLevel = previousLevel
          if (consecutiveFramesOver24Ref.current >= 3) {
            nextLevel = 2
            consecutiveFramesOver24Ref.current = 0
            consecutiveFramesOver16Ref.current = 0
            stableFrameCountRef.current = 0
          } else if (consecutiveFramesOver16Ref.current >= 3 && previousLevel < 1) {
            nextLevel = 1
            consecutiveFramesOver16Ref.current = 0
            stableFrameCountRef.current = 0
          } else if (stableFrameCountRef.current >= 120 && previousLevel > 0) {
            nextLevel = previousLevel === 2 ? 1 : 0
            stableFrameCountRef.current = 0
          }
          if (nextLevel !== previousLevel) {
            setDeferNonCriticalDecorations(nextLevel === 2)
          }
          return nextLevel
        })
      }
      rafId = globalThis.requestAnimationFrame(onFrame)
    }
    rafId = globalThis.requestAnimationFrame(onFrame)
    return () => {
      cancelled = true
      if (rafId) {
        globalThis.cancelAnimationFrame(rafId)
      }
    }
  }, [phase10ComputationEnabled])

  const progressiveBatchSize = useMemo(
    () => effectiveProgressiveBatchSize(budgetDegradeLevel),
    [budgetDegradeLevel],
  )
  const virtualOverscan = useMemo(
    () => effectiveVirtualOverscan(budgetDegradeLevel),
    [budgetDegradeLevel],
  )

  useEffect(() => {
    if (!phase10ComputationEnabled) {
      return
    }
    if (progressiveVisibleCount >= groupedEntries.length) {
      return
    }
    let cancelled = false
    let rafId = 0
    rafId = globalThis.requestAnimationFrame(() => {
      if (cancelled) {
        return
      }
      const frameStart = performance.now()
      setProgressiveVisibleCount((previous) => {
        if (previous >= groupedEntries.length) {
          return previous
        }
        const nextCount = Math.min(groupedEntries.length, previous + progressiveBatchSize)
        const frameDurationMs = Math.max(0, performance.now() - frameStart)
        emitPhase10ProgressiveBatch({
          threadId,
          mode: phase10Mode,
          previousVisibleCount: previous,
          nextVisibleCount: nextCount,
          totalCount: groupedEntries.length,
          batchSize: progressiveBatchSize,
          frameDurationMs,
          frameBudgetMs: PHASE10_PROGRESSIVE_FRAME_BUDGET_MS,
          budgetDegradeLevel,
          virtualized: phase10VirtualizationEnabled,
        })
        return nextCount
      })
    })
    return () => {
      cancelled = true
      if (rafId) {
        globalThis.cancelAnimationFrame(rafId)
      }
    }
  }, [
    budgetDegradeLevel,
    groupedEntries.length,
    phase10ComputationEnabled,
    phase10Mode,
    phase10VirtualizationEnabled,
    progressiveBatchSize,
    progressiveVisibleCount,
    threadId,
  ])

  const streamEntries = useMemo(() => {
    if (!phase10ProgressiveRenderEnabled) {
      return groupedEntries
    }
    const seedCount =
      progressiveVisibleCount > 0
        ? progressiveVisibleCount
        : Math.min(PHASE10_PROGRESSIVE_INITIAL_CHUNK, groupedEntries.length)
    return groupedEntries.slice(0, Math.max(0, seedCount))
  }, [groupedEntries, phase10ProgressiveRenderEnabled, progressiveVisibleCount])
  const streamEntryKeys = useMemo(
    () => streamEntries.map((entry) => getStreamEntryKey(entry)),
    [streamEntries],
  )
  const streamEntryKeysSet = useMemo(() => new Set(streamEntryKeys), [streamEntryKeys])
  const streamEntrySignature = useMemo(() => streamEntryKeys.join('|'), [streamEntryKeys])

  const rowVirtualizer = useVirtualizer({
    count: streamEntries.length,
    getScrollElement: () => containerRef.current,
    estimateSize: (index) => estimateStreamEntrySize(streamEntries[index]),
    overscan: virtualOverscan,
    getItemKey: (index) => getStreamEntryKey(streamEntries[index]),
    measureElement: (element) => element.getBoundingClientRect().height,
    enabled: phase10Mode !== 'off' && streamEntries.length > 0,
    initialRect: { width: 0, height: 720 },
  })

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
    anchorSnapshotRef.current = captureVisibleAnchor(containerRef.current)
  }, [])

  useLayoutEffect(() => {
    autoScrollRef.current = true
    manuallyToggledExpandedRef.current = new Set()
    anchorSnapshotRef.current = null
    if (!threadId) {
      setExpandedItemIds(new Set())
      setDismissedPlanReadyKeys(new Set())
      setProgressiveVisibleCount(0)
      return
    }
    const saved = loadMessagesV3ViewState(threadId)
    setExpandedItemIds(new Set(saved.expandedItemIds))
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
          const hasArguments = Boolean(normalizeText(item.argumentsText))
          const hasOutput = Boolean(normalizeText(item.outputText))
          const hasFiles = item.outputFiles.length > 0
          const hasBody = hasArguments || hasOutput || hasFiles
          const shouldExpand =
            item.status === 'in_progress' ||
            (item.toolType !== 'commandExecution' && hasBody && !isHeavyToolItem(item))
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
        toViewState(expandedItemIds, dismissedPlanReadyKeys),
      )
    }, VIEW_STATE_PERSIST_DEBOUNCE_MS)
    return () => globalThis.clearTimeout(persistTimer)
  }, [dismissedPlanReadyKeys, expandedItemIds, threadId])

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

  const openFullArtifact = useCallback((title: string, content: string) => {
    setFullArtifactView({
      title,
      content,
    })
  }, [])

  const closeFullArtifact = useCallback(() => {
    setFullArtifactView(null)
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
    return `${itemKey}::${pendingKey}::${planKey}::${streamEntrySignature}`
  }, [pendingRequests, snapshot?.uiSignals.planReady, streamEntrySignature, visibleItems])

  useLayoutEffect(() => {
    const container = containerRef.current
    const previousAnchor = container ? anchorSnapshotRef.current : null
    const shouldScroll = autoScrollRef.current || (container ? isNearBottom(container) : true)
    let verificationRafId = 0
    if (!shouldScroll) {
      if (container && previousAnchor && phase10Mode !== 'off') {
        if (!streamEntryKeysSet.has(previousAnchor.entryKey)) {
          emitPhase10AnchorRestore({
            threadId,
            mode: phase10Mode,
            entryKey: previousAnchor.entryKey,
            restored: false,
            appliedScrollAdjustment: false,
            driftPx: null,
            virtualized: phase10VirtualizationEnabled,
            reason: 'anchor_missing',
          })
          if (phase10Mode === 'on') {
            activatePhase10Fallback('anchor_missing', {
              entryKey: previousAnchor.entryKey,
            })
          }
        } else {
          const anchorNode = findStreamEntryNode(container, previousAnchor.entryKey)
          if (!anchorNode) {
            emitPhase10AnchorRestore({
              threadId,
              mode: phase10Mode,
              entryKey: previousAnchor.entryKey,
              restored: false,
              appliedScrollAdjustment: false,
              driftPx: null,
              virtualized: phase10VirtualizationEnabled,
              reason: 'anchor_missing',
            })
            if (phase10Mode === 'on') {
              activatePhase10Fallback('anchor_missing', {
                entryKey: previousAnchor.entryKey,
              })
            }
            if (container) {
              anchorSnapshotRef.current = captureVisibleAnchor(container)
            }
            return () => {
              if (verificationRafId) {
                globalThis.cancelAnimationFrame(verificationRafId)
              }
            }
          }
          const containerTop = container.getBoundingClientRect().top
          const currentOffset = anchorNode.getBoundingClientRect().top - containerTop
          const delta = currentOffset - previousAnchor.offsetWithinViewportPx
          const shouldAdjust = phase10Mode === 'on' && Math.abs(delta) > PHASE10_ANCHOR_RESTORE_TOLERANCE_PX
          if (shouldAdjust) {
            container.scrollTop += delta
          }
          const offsetAfterAdjust = anchorNode.getBoundingClientRect().top - containerTop
          const driftAfterAdjust = offsetAfterAdjust - previousAnchor.offsetWithinViewportPx
          emitPhase10AnchorRestore({
            threadId,
            mode: phase10Mode,
            entryKey: previousAnchor.entryKey,
            restored: Math.abs(driftAfterAdjust) <= PHASE10_ANCHOR_DRIFT_BREAK_PX,
            appliedScrollAdjustment: shouldAdjust,
            driftPx: driftAfterAdjust,
            virtualized: phase10VirtualizationEnabled,
            reason: 'anchor_restored',
          })
          verificationRafId = globalThis.requestAnimationFrame(() => {
            const latestContainer = containerRef.current
            if (!latestContainer) {
              return
            }
            const verifiedAnchorNode = findStreamEntryNode(latestContainer, previousAnchor.entryKey)
            if (!verifiedAnchorNode) {
              emitPhase10AnchorRestore({
                threadId,
                mode: phase10Mode,
                entryKey: previousAnchor.entryKey,
                restored: false,
                appliedScrollAdjustment: shouldAdjust,
                driftPx: null,
                virtualized: phase10VirtualizationEnabled,
                reason: 'anchor_missing_after_stabilization',
              })
              if (phase10Mode === 'on') {
                activatePhase10Fallback('anchor_missing', { entryKey: previousAnchor.entryKey })
              }
              return
            }
            const latestTop = latestContainer.getBoundingClientRect().top
            const verifiedOffset = verifiedAnchorNode.getBoundingClientRect().top - latestTop
            const verifiedDrift = verifiedOffset - previousAnchor.offsetWithinViewportPx
            if (Math.abs(verifiedDrift) > PHASE10_ANCHOR_DRIFT_BREAK_PX) {
              emitPhase10AnchorRestore({
                threadId,
                mode: phase10Mode,
                entryKey: previousAnchor.entryKey,
                restored: false,
                appliedScrollAdjustment: shouldAdjust,
                driftPx: verifiedDrift,
                virtualized: phase10VirtualizationEnabled,
                reason: 'anchor_drift_after_stabilization',
              })
              if (phase10Mode === 'on') {
                activatePhase10Fallback('anchor_drift', {
                  entryKey: previousAnchor.entryKey,
                  driftPx: verifiedDrift,
                })
              }
            }
          })
        }
      }
      if (container) {
        anchorSnapshotRef.current = captureVisibleAnchor(container)
      }
      return () => {
        if (verificationRafId) {
          globalThis.cancelAnimationFrame(verificationRafId)
        }
      }
    }
    if (container) {
      container.scrollTop = container.scrollHeight
      anchorSnapshotRef.current = captureVisibleAnchor(container)
      return () => {
        if (verificationRafId) {
          globalThis.cancelAnimationFrame(verificationRafId)
        }
      }
    }
    bottomRef.current?.scrollIntoView({ block: 'end' })
    return () => {
      if (verificationRafId) {
        globalThis.cancelAnimationFrame(verificationRafId)
      }
    }
  }, [
    activatePhase10Fallback,
    phase10Mode,
    phase10VirtualizationEnabled,
    scrollKey,
    snapshot?.activeTurnId,
    snapshot?.processingState,
    streamEntryKeysSet,
    threadId,
  ])

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
    resolveSnapshotThreadRole(snapshot) === 'execution' &&
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
          <div className={styles.streamEntry}>
            {renderItemRowV3({
              item: entry.item,
              requestMapByRequestId,
              reasoningMeta,
              expandedItemIds,
              onToggleExpanded: toggleExpanded,
              onRequestAutoScroll: requestAutoScroll,
              onOpenFullArtifact: openFullArtifact,
              streamingTextLaneByItemId,
            })}
          </div>
        )
      }

      return (
        <section
          className={`${styles.row} ${styles.rowCard}`}
          data-testid={`conversation-v3-tool-group-${entry.group.id}`}
        >
          <div className={styles.rowRail}>
            <div className={`${styles.groupShell} ${styles.groupShellStream}`}>
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
                        onOpenFullArtifact: openFullArtifact,
                        streamingTextLaneByItemId,
                      })}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </section>
      )
    },
    [
      expandedItemIds,
      requestMapByRequestId,
      requestAutoScroll,
      toggleExpanded,
      openFullArtifact,
      streamingTextLaneByItemId,
      visibleState.reasoningMetaById,
    ],
  )
  const virtualItems = rowVirtualizer.getVirtualItems()
  const shouldRenderVirtualizedStream = phase10VirtualizationEnabled
  const virtualBootstrapEntries = useMemo(() => {
    if (!shouldRenderVirtualizedStream || virtualItems.length > 0) {
      return [] as ToolGroupEntryV3[]
    }
    return streamEntries.slice(0, Math.min(streamEntries.length, PHASE10_VIRTUAL_BOOTSTRAP_COUNT))
  }, [shouldRenderVirtualizedStream, streamEntries, virtualItems.length])
  const showNonCriticalSuffix = !deferNonCriticalDecorations

  return (
    <div
      ref={containerRef}
      className={`${styles.feed} ${threadChatFlatCanvas ? styles.feedThreadChatCanvas : ''}`}
      data-testid="messages-v3-feed"
      onScroll={updateAutoScroll}
    >
      {prefix}

      {streamEntries.length === 0 && pendingRequestCards.length === 0 && !isLoading ? (
        <div className={styles.empty}>No conversation items yet.</div>
      ) : null}

      {hasOlderHistory && onLoadMoreHistory ? (
        <div className={styles.loadMoreRow}>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={onLoadMoreHistory}
            disabled={isLoadingHistory}
            data-testid="messages-v3-load-more-history"
          >
            {isLoadingHistory ? 'Loading older messages...' : 'Load older messages'}
          </button>
        </div>
      ) : null}

      <div
        className={styles.streamStack}
        data-testid="messages-v3-stream-stack"
        data-phase10-mode={phase10Mode}
        data-phase10-fallback={threadFallbackReason ?? ''}
        data-phase10-degrade-level={String(budgetDegradeLevel)}
      >
        {shouldRenderVirtualizedStream ? (
          <div
            className={styles.virtualizedViewport}
            data-testid="messages-v3-virtualized-viewport"
            style={{ height: `${rowVirtualizer.getTotalSize()}px` }}
          >
            {virtualItems.length > 0
              ? virtualItems.map((virtualItem) => {
                  const entry = streamEntries[virtualItem.index]
                  if (!entry) {
                    return null
                  }
                  const entryKey = getStreamEntryKey(entry)
                  return (
                    <div
                      key={String(virtualItem.key)}
                      ref={(node) => {
                        if (node) {
                          rowVirtualizer.measureElement(node)
                        }
                      }}
                      className={styles.streamVirtualItemHost}
                      data-testid="messages-v3-stream-entry-host"
                      data-index={String(virtualItem.index)}
                      data-stream-entry-key={entryKey}
                      data-stream-entry-index={String(virtualItem.index)}
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        width: '100%',
                        transform: `translateY(${virtualItem.start}px)`,
                      }}
                    >
                      {renderGroupedEntry(entry)}
                    </div>
                  )
                })
              : virtualBootstrapEntries.map((entry, index) => {
                  const entryKey = getStreamEntryKey(entry)
                  return (
                    <div
                      key={`bootstrap:${entryKey}`}
                      className={styles.streamEntryHost}
                      data-testid="messages-v3-stream-entry-host"
                      data-stream-entry-key={entryKey}
                      data-stream-entry-index={String(index)}
                    >
                      {renderGroupedEntry(entry)}
                    </div>
                  )
                })}
          </div>
        ) : (
          streamEntries.map((entry, index) => {
            const entryKey = getStreamEntryKey(entry)
            return (
              <div
                key={entryKey}
                className={styles.streamEntryHost}
                data-testid="messages-v3-stream-entry-host"
                data-stream-entry-key={entryKey}
                data-stream-entry-index={String(index)}
              >
                {renderGroupedEntry(entry)}
              </div>
            )
          })
        )}
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

      {isLoading && streamEntries.length === 0 ? (
        <div className={styles.empty}>Loading conversation...</div>
      ) : null}

      {suffix && showNonCriticalSuffix ? <div className={styles.feedSuffix}>{suffix}</div> : null}

      {fullArtifactView ? (
        <div
          className={styles.fullArtifactOverlay}
          role="dialog"
          aria-modal="true"
          aria-label={fullArtifactView.title}
          onClick={closeFullArtifact}
        >
          <div className={styles.fullArtifactModal} onClick={(event) => event.stopPropagation()}>
            <div className={styles.fullArtifactHeader}>
              <h3 className={styles.fullArtifactTitle}>{fullArtifactView.title}</h3>
              <button type="button" className={styles.secondaryButton} onClick={closeFullArtifact}>
                Close
              </button>
            </div>
            <pre className={styles.fullArtifactPre}>{fullArtifactView.content}</pre>
          </div>
        </div>
      ) : null}

      <div ref={bottomRef} />
    </div>
  )
}








