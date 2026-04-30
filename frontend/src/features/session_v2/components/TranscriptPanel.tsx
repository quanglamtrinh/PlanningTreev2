import { useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import { DocumentRichViewContent } from '../../markdown/DocumentRichView'
import { SharedMarkdownRenderer } from '../../markdown/SharedMarkdownRenderer'
import { isItemKind } from '../contracts'
import type { ItemKind, SessionItem, SessionTurn, VisibleTranscriptRow } from '../contracts'
import { formatNodeTitleWithIndex } from '../../../utils/nodeDisplayIndex'

type TranscriptPanelProps = {
  threadId: string | null
  turns: SessionTurn[]
  itemsByTurn: Record<string, SessionItem[]>
  visibleRows?: VisibleTranscriptRow[]
  workflowContextItem?: SessionItem | null
  showWorkflowContext?: boolean
}

type TranscriptRow =
  | {
      key: string
      type: 'item'
      item: SessionItem
    }
  | {
      key: string
      type: 'toolSummary'
      summary: string
    }
  | {
      key: string
      type: 'compactMarker'
    }
  | {
      key: string
      type: 'turnFileSummary'
      summary: TurnFileSummary
    }
  | {
      key: string
      type: 'agentWorkSummary'
      entries: AgentWorkSummaryEntry[]
    }

type RowVariant = 'user' | 'assistant' | 'tool' | 'unknown'

type AgentWorkSummaryEntry =
  | {
      key: string
      type: 'item'
      item: SessionItem
    }
  | {
      key: string
      type: 'toolSummary'
      summary: string
    }
  | {
      key: string
      type: 'compactMarker'
    }

type FileChangeStats = {
  created: number
  edited: number
  deleted: number
  renamed: number
}

type DiffStats = {
  added: number
  removed: number
}

type TurnFileChangeEntry = {
  path: string
  changeType: 'created' | 'updated' | 'deleted'
  added: number
  removed: number
  summary: string | null
  diffText: string | null
}

type TurnFileSummary = {
  fileCount: number
  added: number
  removed: number
  entries: TurnFileChangeEntry[]
}

type RenderableDiffLine = {
  kind: 'added' | 'removed' | 'context'
  lineNumber: number | null
  text: string
}

const USER_MESSAGE_COLLAPSE_CHAR_LIMIT = 1100
const USER_MESSAGE_COLLAPSE_LINE_LIMIT = 14
const SCROLL_SNAPSHOT_DEBOUNCE_MS = 120
const AUTO_FOLLOW_BOTTOM_THRESHOLD_PX = 64
const LIVE_TOOL_PREVIEW_MAX_CHARS = 120
const DIFF_KEYWORD_RE =
  /\b(import|export|const|let|var|function|return|async|await|new|from|default|class|extends|interface|type|if|else|for|while|switch|case|try|catch|finally|throw|break|continue|public|private|protected|readonly|static|implements|enum)\b/g
const DIFF_NUMBER_RE = /\b(?:\d+\.?\d*|\.\d+)\b/g

type ThreadScrollSnapshot = {
  top: number
  fromBottom: number
}

const threadScrollSnapshots = new Map<string, ThreadScrollSnapshot>()

function rememberThreadScrollPosition(threadId: string, element: HTMLElement): void {
  const maxTop = Math.max(0, element.scrollHeight - element.clientHeight)
  const top = Math.min(maxTop, Math.max(0, element.scrollTop))
  const fromBottom = Math.max(0, element.scrollHeight - element.clientHeight - top)
  threadScrollSnapshots.set(threadId, { top, fromBottom })
}

function isScrollNearBottom(element: HTMLElement): boolean {
  const maxTop = Math.max(0, element.scrollHeight - element.clientHeight)
  const clampedTop = Math.min(maxTop, Math.max(0, element.scrollTop))
  const fromBottom = Math.max(0, maxTop - clampedTop)
  return fromBottom <= AUTO_FOLLOW_BOTTOM_THRESHOLD_PX
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object'
}

function shortenPath(rawPath: string): string {
  const normalized = rawPath.replace(/\\/g, '/')
  // Try to strip common absolute path prefixes to get a workspace-relative path
  const homeMatch = normalized.match(/^\/(?:Users|home)\/[^/]+\/(.+)$/)
  if (homeMatch) {
    return homeMatch[1]
  }
  // Windows: strip drive + Users/username prefix
  const winMatch = normalized.match(/^[A-Za-z]:\/(?:Users|home)\/[^/]+\/(.+)$/i)
  if (winMatch) {
    return winMatch[1]
  }
  return normalized
}

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function payloadTypeOf(item: SessionItem): string {
  const payload = isRecord(item.payload) ? item.payload : {}
  return normalizeText(payload.type)
}

function normalizedKindOf(item: SessionItem): ItemKind | null {
  if (isItemKind(item.normalizedKind)) {
    return item.normalizedKind
  }
  if (isItemKind(item.kind)) {
    return item.kind
  }
  const payloadType = payloadTypeOf(item)
  return isItemKind(payloadType) ? payloadType : null
}

function pluralize(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`
}

function lowercaseFirst(text: string): string {
  if (!text) {
    return ''
  }
  return `${text.charAt(0).toLowerCase()}${text.slice(1)}`
}

function toSingleLinePreview(text: string, maxChars: number): string {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (!normalized) {
    return ''
  }
  if (normalized.length <= maxChars) {
    return normalized
  }
  return `${normalized.slice(0, Math.max(0, maxChars - 3)).trimEnd()}...`
}

function normalizeDiffText(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null
  }
  const normalized = value.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
  return normalized ? normalized : null
}

function diffStatsFromText(text: string): DiffStats {
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  let added = 0
  let removed = 0
  for (const line of normalized.split('\n')) {
    if (!line || line.startsWith('+++') || line.startsWith('---')) {
      continue
    }
    if (line.startsWith('+')) {
      added += 1
      continue
    }
    if (line.startsWith('-')) {
      removed += 1
    }
  }
  return { added, removed }
}

function diffStatsFromSummary(text: string | null): DiffStats {
  if (!text) {
    return { added: 0, removed: 0 }
  }
  const ins = text.match(/(\d+)\s+insertions?\b/i)
  const dels = text.match(/(\d+)\s+deletions?\b/i)
  return {
    added: ins ? Number(ins[1]) : 0,
    removed: dels ? Number(dels[1]) : 0,
  }
}

function normalizeChangeType(value: unknown): 'created' | 'updated' | 'deleted' {
  const normalized = normalizeText(value).toLowerCase()
  if (
    normalized === 'add' ||
    normalized === 'added' ||
    normalized === 'create' ||
    normalized === 'created' ||
    normalized === 'new'
  ) {
    return 'created'
  }
  if (
    normalized === 'delete' ||
    normalized === 'deleted' ||
    normalized === 'remove' ||
    normalized === 'removed'
  ) {
    return 'deleted'
  }
  return 'updated'
}

function mergeDiffText(existing: string | null, next: string | null): string | null {
  if (!existing) {
    return next
  }
  if (!next) {
    return existing
  }
  if (existing.includes(next)) {
    return existing
  }
  return `${existing}\n${next}`
}

function parseUnifiedDiffHunkHeader(line: string): { oldStart: number; newStart: number } | null {
  const match = line.match(/^@@\s+\-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@/)
  if (!match) {
    return null
  }
  return {
    oldStart: Number(match[1]),
    newStart: Number(match[2]),
  }
}

function isDiffMetadataLine(line: string): boolean {
  return (
    line.startsWith('diff --git ') ||
    line.startsWith('index ') ||
    line.startsWith('--- ') ||
    line.startsWith('+++ ') ||
    line.startsWith('*** ')
  )
}

function buildRenderableDiffLines(diffText: string | null): RenderableDiffLine[] {
  if (!diffText) {
    return []
  }
  const normalized = diffText.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
  if (!normalized) {
    return []
  }

  const lines = normalized.split('\n')
  const rendered: RenderableDiffLine[] = []
  let oldLineNumber = 1
  let newLineNumber = 1

  for (const line of lines) {
    const hunk = parseUnifiedDiffHunkHeader(line)
    if (hunk) {
      oldLineNumber = hunk.oldStart
      newLineNumber = hunk.newStart
      continue
    }
    if (isDiffMetadataLine(line)) {
      continue
    }
    if (line.startsWith('+') && !line.startsWith('+++')) {
      rendered.push({
        kind: 'added',
        lineNumber: newLineNumber > 0 ? newLineNumber : null,
        text: line.slice(1),
      })
      if (newLineNumber > 0) {
        newLineNumber += 1
      }
      continue
    }
    if (line.startsWith('-') && !line.startsWith('---')) {
      rendered.push({
        kind: 'removed',
        lineNumber: oldLineNumber > 0 ? oldLineNumber : null,
        text: line.slice(1),
      })
      if (oldLineNumber > 0) {
        oldLineNumber += 1
      }
      continue
    }
    const contextText = line.startsWith(' ') ? line.slice(1) : line
    rendered.push({
      kind: 'context',
      lineNumber: newLineNumber > 0 ? newLineNumber : null,
      text: contextText,
    })
    if (oldLineNumber > 0) {
      oldLineNumber += 1
    }
    if (newLineNumber > 0) {
      newLineNumber += 1
    }
  }

  return rendered
}

function highlightCodeSegment(segment: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const keywordRe = new RegExp(DIFF_KEYWORD_RE.source, 'g')
  let cursor = 0
  let match: RegExpExecArray | null
  while ((match = keywordRe.exec(segment)) !== null) {
    if (match.index > cursor) {
      const plainChunk = segment.slice(cursor, match.index)
      nodes.push(...highlightNumberChunk(plainChunk, `${keyPrefix}:plain:${cursor}`))
    }
    nodes.push(
      <span key={`${keyPrefix}:kw:${match.index}`} className="sessionV2DiffTokKeyword">
        {match[1]}
      </span>,
    )
    cursor = match.index + match[0].length
  }
  if (cursor < segment.length) {
    nodes.push(...highlightNumberChunk(segment.slice(cursor), `${keyPrefix}:tail`))
  }
  if (nodes.length === 0) {
    nodes.push(
      <span key={`${keyPrefix}:empty`} className="sessionV2DiffTokPlain">
        {segment}
      </span>,
    )
  }
  return nodes
}

function highlightNumberChunk(chunk: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const numberRe = new RegExp(DIFF_NUMBER_RE.source, 'g')
  let cursor = 0
  let match: RegExpExecArray | null
  while ((match = numberRe.exec(chunk)) !== null) {
    if (match.index > cursor) {
      nodes.push(
        <span key={`${keyPrefix}:plain:${cursor}`} className="sessionV2DiffTokPlain">
          {chunk.slice(cursor, match.index)}
        </span>,
      )
    }
    nodes.push(
      <span key={`${keyPrefix}:num:${match.index}`} className="sessionV2DiffTokNumber">
        {match[0]}
      </span>,
    )
    cursor = match.index + match[0].length
  }
  if (cursor < chunk.length) {
    nodes.push(
      <span key={`${keyPrefix}:plain:end`} className="sessionV2DiffTokPlain">
        {chunk.slice(cursor)}
      </span>,
    )
  }
  if (nodes.length === 0) {
    nodes.push(
      <span key={`${keyPrefix}:plain:full`} className="sessionV2DiffTokPlain">
        {chunk}
      </span>,
    )
  }
  return nodes
}

function highlightDiffCodeLine(line: string, lineKey: string): ReactNode {
  const parts = line.split(/('[^']*'|"[^"]*"|`[^`]*`)/g)
  const rendered: ReactNode[] = []
  parts.forEach((part, index) => {
    if (!part) {
      return
    }
    if (/^['"`]/.test(part)) {
      rendered.push(
        <span key={`${lineKey}:str:${index}`} className="sessionV2DiffTokString">
          {part}
        </span>,
      )
      return
    }
    rendered.push(...highlightCodeSegment(part, `${lineKey}:seg:${index}`))
  })
  if (rendered.length === 0) {
    return <span className="sessionV2DiffTokPlain">{line}</span>
  }
  return <>{rendered}</>
}

function extractUserContent(content: unknown): string {
  if (!Array.isArray(content)) {
    return ''
  }
  const rows: string[] = []
  for (const entry of content) {
    if (!isRecord(entry)) {
      continue
    }
    const type = normalizeText(entry.type)
    if (type === 'text' || type === 'input_text' || type === 'output_text') {
      const text = normalizeText(entry.text)
      if (text) {
        rows.push(text)
      }
      continue
    }
    if (type === 'image') {
      const imageUrl = normalizeText(entry.imageUrl ?? entry.image_url)
      if (imageUrl) {
        rows.push(`[Image] ${imageUrl}`)
      }
      continue
    }
    if (type === 'localImage') {
      const path = normalizeText(entry.path)
      if (path) {
        rows.push(`[Local image] ${path}`)
      }
      continue
    }
    const fallbackText = normalizeText(entry.text ?? entry.output)
    if (fallbackText) {
      rows.push(fallbackText)
    }
  }
  return rows.join('\n').trim()
}

function extractReasoningContent(payload: Record<string, unknown>): string {
  const summary = Array.isArray(payload.summary)
    ? payload.summary.filter((entry): entry is string => typeof entry === 'string')
    : []
  const content = Array.isArray(payload.content)
    ? payload.content.filter((entry): entry is string => typeof entry === 'string')
    : []
  const combined = [...summary, ...content].map((entry) => entry.trim()).filter(Boolean)
  return combined.join('\n').trim()
}

function extractFileChanges(payload: Record<string, unknown>): string {
  const changes = payload.changes
  if (!Array.isArray(changes)) {
    return ''
  }
  const lines: string[] = []
  for (const change of changes) {
    if (!isRecord(change)) {
      continue
    }
    const path = normalizeText(change.path)
    const kind = normalizeText(change.kind || change.changeType)
    if (!path) {
      continue
    }
    lines.push(kind ? `${kind}: ${path}` : path)
  }
  return lines.join('\n').trim()
}

function formatPayloadFallback(payload: Record<string, unknown>): string {
  const json = JSON.stringify(payload, null, 2)
  return json === '{}' ? '' : json
}

function extractContentText(record: Record<string, unknown>): string {
  return Array.isArray(record.content) ? extractUserContent(record.content) : ''
}

function renderItemText(item: SessionItem): string {
  const payload = isRecord(item.payload) ? item.payload : {}
  const itemKind = normalizedKindOf(item)

  if (itemKind === 'userMessage') {
    const text = extractUserContent(payload.content)
    return text || normalizeText(payload.text)
  }
  if (itemKind === 'agentMessage' || itemKind === 'plan') {
    return normalizeText(payload.text) || normalizeText(payload.delta)
  }
  if (itemKind === 'reasoning') {
    return extractReasoningContent(payload)
  }
  if (itemKind === 'commandExecution') {
    const aggregated = normalizeText(payload.aggregatedOutput || payload.output)
    if (aggregated) {
      return aggregated
    }
    return normalizeText(payload.command)
  }
  if (itemKind === 'fileChange') {
    const output = normalizeText(payload.output)
    if (output) {
      return output
    }
    const changes = extractFileChanges(payload)
    if (changes) {
      return changes
    }
  }

  if (typeof payload.text === 'string') {
    return payload.text
  }
  if (Array.isArray(payload.content)) {
    const contentText = extractUserContent(payload.content)
    if (contentText) {
      return contentText
    }
  }
  if (typeof payload.aggregatedOutput === 'string') {
    return payload.aggregatedOutput
  }
  if (typeof payload.output === 'string') {
    return payload.output
  }
  if (typeof payload.delta === 'string') {
    return payload.delta
  }
  if (itemKind === 'fileChange') {
    const changes = extractFileChanges(payload)
    if (changes) {
      return changes
    }
  }

  return formatPayloadFallback(payload)
}

function resolveRowVariant(item: SessionItem): RowVariant {
  const itemKind = normalizedKindOf(item)
  if (itemKind === 'userMessage') {
    return 'user'
  }
  if (
    itemKind === 'agentMessage' ||
    itemKind === 'plan' ||
    itemKind === 'reasoning'
  ) {
    return 'assistant'
  }
  if (itemKind === null) {
    return 'unknown'
  }
  return 'tool'
}

function isContextCompactionItem(item: SessionItem): boolean {
  return payloadTypeOf(item) === 'contextCompaction'
}

function isWorkflowContextItem(item: SessionItem): boolean {
  const payload = isRecord(item.payload) ? item.payload : {}
  const metadata = isRecord(payload.metadata) ? payload.metadata : {}
  if (metadata.workflowContext === true) {
    return true
  }
  const rawItem = isRecord(item.rawItem) ? (item.rawItem as Record<string, unknown>) : {}
  const rawMetadata = isRecord(rawItem.metadata) ? rawItem.metadata : {}
  return rawMetadata.workflowContext === true
}

function workflowContextMetadata(item: SessionItem): Record<string, unknown> {
  const payload = isRecord(item.payload) ? item.payload : {}
  const metadata = isRecord(payload.metadata) ? payload.metadata : {}
  if (metadata.workflowContext === true) {
    return metadata
  }
  const rawItem = isRecord(item.rawItem) ? (item.rawItem as Record<string, unknown>) : {}
  const rawMetadata = isRecord(rawItem.metadata) ? rawItem.metadata : {}
  return rawMetadata
}

function workflowContextPayload(item: SessionItem): Record<string, unknown> | null {
  const metadata = workflowContextMetadata(item)
  const contextPayload = metadata.contextPayload
  if (isRecord(contextPayload) && isRecord(contextPayload.artifactContext)) {
    return contextPayload
  }
  if (isRecord(contextPayload)) {
    const nextContext = contextPayload.nextContext
    if (isRecord(nextContext) && isRecord(nextContext.payload)) {
      return nextContext.payload
    }
    return contextPayload
  }
  const packet = metadata.nextContext
  if (isRecord(packet) && isRecord(packet.payload)) {
    return packet.payload
  }
  return planningContextPayloadFromText(item)
}

function planningContextPayloadFromText(item: SessionItem): Record<string, unknown> | null {
  const payload = isRecord(item.payload) ? item.payload : {}
  const rawItem = isRecord(item.rawItem) ? (item.rawItem as Record<string, unknown>) : {}
  const text =
    normalizeText(payload.text) ||
    normalizeText(rawItem.text) ||
    extractContentText(payload) ||
    extractContentText(rawItem)
  if (!text) {
    return null
  }
  const match = text.match(/<planning_tree_context\b[^>]*>\s*([\s\S]*?)\s*<\/planning_tree_context>/)
  if (!match) {
    return null
  }
  try {
    const packet = JSON.parse(match[1]) as unknown
    if (!isRecord(packet)) {
      return null
    }
    if (packet.kind === 'context_update') {
      const updatePayload = packet.payload
      const nextContext = isRecord(updatePayload) ? updatePayload.nextContext : null
      if (isRecord(nextContext) && isRecord(nextContext.payload)) {
        return nextContext.payload
      }
    }
    return isRecord(packet.payload) ? packet.payload : null
  } catch {
    return null
  }
}

function nodeTitle(node: unknown): string {
  if (!isRecord(node)) {
    return 'Untitled node'
  }
  return formatNodeTitleWithIndex({
    hierarchical_number: normalizeText(node.hierarchical_number),
    is_init_node: node.is_init_node === true,
    node_kind: normalizeText(node.node_kind),
    title: normalizeText(node.title),
    node_id: normalizeText(node.node_id),
  })
}

function documentContent(document: unknown): string {
  if (!isRecord(document)) {
    return ''
  }
  return typeof document.content === 'string' ? document.content.trim() : ''
}

function clarifyQuestions(clarify: unknown): Record<string, unknown>[] {
  if (!isRecord(clarify) || !Array.isArray(clarify.questions)) {
    return []
  }
  return clarify.questions.filter((question): question is Record<string, unknown> => isRecord(question))
}

function clarifyAnswerText(question: Record<string, unknown>): string {
  const selectedOptionId =
    normalizeText(question.selected_option_id) ||
    normalizeText(question.selectedOptionId) ||
    normalizeText(question.selectedOption)
  if (selectedOptionId && Array.isArray(question.options)) {
    const selectedOption = question.options.find(
      (option): option is Record<string, unknown> =>
        isRecord(option) && normalizeText(option.id) === selectedOptionId,
    )
    const selectedLabel =
      normalizeText(selectedOption?.label) ||
      normalizeText(selectedOption?.value) ||
      normalizeText(selectedOption?.id)
    if (selectedLabel) {
      return selectedLabel
    }
  }

  return (
    normalizeText(question.answer) ||
    normalizeText(question.custom_answer) ||
    normalizeText(question.customAnswer) ||
    normalizeText(question.value) ||
    'Not answered'
  )
}


function splitChildren(split: unknown): Record<string, unknown>[] {
  if (!isRecord(split) || !Array.isArray(split.children)) {
    return []
  }
  return split.children.filter((child): child is Record<string, unknown> => isRecord(child))
}

function artifactContextFromPayload(contextPayload: Record<string, unknown>): Record<string, unknown> {
  if (isRecord(contextPayload.artifactContext)) {
    return contextPayload.artifactContext
  }
  const taskContext = isRecord(contextPayload.taskContext) ? contextPayload.taskContext : null
  const parentPrompts = Array.isArray(taskContext?.parent_chain_prompts)
    ? taskContext.parent_chain_prompts.filter((prompt): prompt is string => typeof prompt === 'string' && prompt.trim().length > 0)
    : []
  const parentNode = isRecord(contextPayload.parentNode) ? contextPayload.parentNode : null
  const currentFrame = isRecord(contextPayload.frame) ? contextPayload.frame : null
  const currentSpec = isRecord(contextPayload.spec) ? contextPayload.spec : null
  const currentNode = isRecord(contextPayload.node) ? contextPayload.node : null
  if (parentPrompts.length > 0 || currentFrame || currentSpec || currentNode) {
    return {
      ancestorContext: parentPrompts.map((prompt, index) => ({
        node: index === parentPrompts.length - 1 && parentNode ? parentNode : { title: `Parent ${index + 1}` },
        summary: prompt,
        frame: { content: prompt },
        clarify: { questions: [] },
        split: { children: [] },
      })),
      currentContext: {
        node: currentNode,
        frame: currentFrame
          ? {
              ...currentFrame,
              content: normalizeText(currentFrame.confirmedContent) || normalizeText(currentFrame.content),
            }
          : null,
        spec: currentSpec
          ? {
              ...currentSpec,
              content: normalizeText(currentSpec.confirmedContent) || normalizeText(currentSpec.content),
            }
          : null,
      },
    }
  }
  return {}
}

function ArtifactDocumentSection({ title, content }: { title: string; content: string }) {
  if (!content) {
    return null
  }
  return (
    <section className="sessionV2WorkflowContextDocument">
      <h5 className="sessionV2WorkflowContextDocumentTitle">{title}</h5>
      <DocumentRichViewContent
        content={content}
        testId={`workflow-context-document-${title}`}
        className="sessionV2WorkflowContextRichView"
      />
    </section>
  )
}

function WorkflowContextNodeSection({
  entry,
  isCurrent,
}: {
  entry: Record<string, unknown>
  isCurrent?: boolean
}) {
  const frameText = documentContent(entry.frame)
  const specText = documentContent(entry.spec)
  const questions = clarifyQuestions(entry.clarify)
  const children = splitChildren(entry.split)
  const hasContent = Boolean(frameText || specText || questions.length > 0 || children.length > 0)
  if (!hasContent) {
    return null
  }
  return (
    <section className="sessionV2WorkflowContextNode">
      <h4>
        {nodeTitle(entry.node)}
        {isCurrent ? <span>current task</span> : null}
      </h4>
      <ArtifactDocumentSection title="frame.md" content={frameText} />
      <ArtifactDocumentSection title="spec.md" content={specText} />
      {questions.length > 0 ? (
        <section className="sessionV2WorkflowContextSection">
          <h5>Clarify</h5>
          <ol>
            {questions.map((question, questionIndex) => (
              <li key={`clarify-${questionIndex}`}>
                <strong>{normalizeText(question.question) || normalizeText(question.field_name) || 'Question'}</strong>
                <span>{clarifyAnswerText(question)}</span>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      {children.length > 0 ? (
        <section className="sessionV2WorkflowContextSection">
          <h5>Split</h5>
          <ul>
            {children.map((child, childIndex) => (
              <li key={`split-${childIndex}`}>
                {nodeTitle(child)}
                {child.isCurrentPath === true ? ' (current path)' : ''}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  )
}

export function WorkflowContextCard({ item, sticky = false }: { item: SessionItem; sticky?: boolean }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const contextPayload = workflowContextPayload(item)
  const artifactContext = contextPayload ? artifactContextFromPayload(contextPayload) : {}
  const ancestorContext = Array.isArray(artifactContext.ancestorContext)
    ? artifactContext.ancestorContext.filter(isRecord)
    : []
  const currentContext = isRecord(artifactContext.currentContext)
    ? artifactContext.currentContext
    : null
  if (!contextPayload) {
    return null
  }
  const hasRenderableContext =
    ancestorContext.some((entry) => Boolean(documentContent(entry.frame) || clarifyQuestions(entry.clarify).length > 0 || splitChildren(entry.split).length > 0)) ||
    Boolean(currentContext && (documentContent(currentContext.frame) || documentContent(currentContext.spec)))
  if (!hasRenderableContext) {
    return null
  }

  return (
    <article
      className={`sessionV2ToolCard sessionV2WorkflowContextCard ${sticky ? 'sessionV2WorkflowContextCardSticky' : ''}`}
      data-testid="workflow-context-card"
    >
      <button
        type="button"
        className="sessionV2WorkflowContextToggle"
        aria-expanded={isExpanded}
        onClick={() => setIsExpanded((value) => !value)}
      >
        <span className="sessionV2WorkflowContextTitle">Context</span>
      </button>
      {isExpanded ? (
        <div className="sessionV2WorkflowContextBody">
          {ancestorContext.map((entry, index) => (
            <WorkflowContextNodeSection key={`ancestor-${index}`} entry={entry} />
          ))}
          {currentContext ? (
            <WorkflowContextNodeSection entry={currentContext} isCurrent />
          ) : null}
        </div>
      ) : null}
    </article>
  )
}

function isToolItem(item: SessionItem): boolean {
  return !isContextCompactionItem(item) && resolveRowVariant(item) === 'tool'
}

function isAgentMessageItem(item: SessionItem): boolean {
  return normalizedKindOf(item) === 'agentMessage'
}

function isFileChangeItem(item: SessionItem): boolean {
  return normalizedKindOf(item) === 'fileChange'
}

function parseFileChangeEntriesFromPayload(payload: Record<string, unknown>): TurnFileChangeEntry[] {
  const rawChanges =
    Array.isArray(payload.changes) ? payload.changes : Array.isArray(payload.files) ? payload.files : []
  const entries: TurnFileChangeEntry[] = []
  for (const rawChange of rawChanges) {
    if (!isRecord(rawChange)) {
      continue
    }
    const path = normalizeText(rawChange.path)
    if (!path) {
      continue
    }
    const summary = normalizeText(rawChange.summary) || null
    const diff =
      normalizeDiffText(rawChange.diff) ??
      normalizeDiffText(rawChange.patchText) ??
      normalizeDiffText(rawChange.patch_text)
    const diffStats = diff ? diffStatsFromText(diff) : diffStatsFromSummary(summary)
    entries.push({
      path,
      changeType: normalizeChangeType(rawChange.kind || rawChange.changeType),
      added: diffStats.added,
      removed: diffStats.removed,
      summary,
      diffText: diff,
    })
  }
  return entries
}

function summarizeTurnFileChanges(items: SessionItem[]): TurnFileSummary | null {
  const byPath = new Map<string, TurnFileChangeEntry>()
  for (const item of items) {
    if (!isFileChangeItem(item)) {
      continue
    }
    const payload = isRecord(item.payload) ? item.payload : {}
    const entries = parseFileChangeEntriesFromPayload(payload)
    for (const entry of entries) {
      const existing = byPath.get(entry.path)
      if (!existing) {
        byPath.set(entry.path, { ...entry })
        continue
      }
      byPath.set(entry.path, {
        ...existing,
        changeType: entry.changeType === 'deleted' ? 'deleted' : entry.changeType === 'created' ? 'created' : existing.changeType,
        added: existing.added + entry.added,
        removed: existing.removed + entry.removed,
        summary: entry.summary ?? existing.summary,
        diffText: mergeDiffText(existing.diffText, entry.diffText),
      })
    }
  }

  const entries = [...byPath.values()]
  if (entries.length === 0) {
    return null
  }
  const totals = entries.reduce(
    (acc, entry) => ({
      added: acc.added + entry.added,
      removed: acc.removed + entry.removed,
    }),
    { added: 0, removed: 0 },
  )
  return {
    fileCount: entries.length,
    added: totals.added,
    removed: totals.removed,
    entries,
  }
}

function isTerminalTurn(turn: SessionTurn): boolean {
  return turn.status === 'completed' || turn.status === 'failed' || turn.status === 'interrupted'
}

function parseFileChangeStats(payload: Record<string, unknown>): FileChangeStats {
  const stats: FileChangeStats = {
    created: 0,
    edited: 0,
    deleted: 0,
    renamed: 0,
  }
  const changes = payload.changes
  if (!Array.isArray(changes)) {
    return stats
  }
  let counted = 0
  for (const change of changes) {
    if (!isRecord(change)) {
      continue
    }
    const rawKind = normalizeText(change.kind || change.changeType).toLowerCase()
    if (rawKind === 'add' || rawKind === 'added' || rawKind === 'create' || rawKind === 'created' || rawKind === 'new') {
      stats.created += 1
      counted += 1
      continue
    }
    if (
      rawKind === 'delete' ||
      rawKind === 'deleted' ||
      rawKind === 'remove' ||
      rawKind === 'removed'
    ) {
      stats.deleted += 1
      counted += 1
      continue
    }
    if (rawKind === 'rename' || rawKind === 'renamed' || rawKind === 'move' || rawKind === 'moved') {
      stats.renamed += 1
      counted += 1
      continue
    }
    if (normalizeText(change.path)) {
      stats.edited += 1
      counted += 1
    }
  }
  if (counted === 0 && changes.length > 0) {
    stats.edited = changes.length
  }
  return stats
}

function summarizeToolItems(items: SessionItem[]): string {
  let commandCount = 0
  let otherToolCount = 0
  const fileStats: FileChangeStats = {
    created: 0,
    edited: 0,
    deleted: 0,
    renamed: 0,
  }

  for (const item of items) {
    const payload = isRecord(item.payload) ? item.payload : {}
    const payloadType = normalizeText(payload.type)
    const kind = payloadType || item.kind

    if (kind === 'commandExecution') {
      commandCount += 1
      continue
    }
    if (kind === 'fileChange') {
      const stats = parseFileChangeStats(payload)
      const fileTotal = stats.created + stats.edited + stats.deleted + stats.renamed
      if (fileTotal === 0) {
        fileStats.edited += 1
      } else {
        fileStats.created += stats.created
        fileStats.edited += stats.edited
        fileStats.deleted += stats.deleted
        fileStats.renamed += stats.renamed
      }
      continue
    }

    otherToolCount += 1
  }

  const parts: string[] = []
  if (fileStats.created > 0) {
    parts.push(`Created ${pluralize(fileStats.created, 'file', 'files')}`)
  }
  if (fileStats.deleted > 0) {
    parts.push(`Deleted ${pluralize(fileStats.deleted, 'file', 'files')}`)
  }
  if (fileStats.renamed > 0) {
    parts.push(`Renamed ${pluralize(fileStats.renamed, 'file', 'files')}`)
  }
  if (fileStats.edited > 0) {
    parts.push(`Edited ${pluralize(fileStats.edited, 'file', 'files')}`)
  }
  if (commandCount > 0) {
    parts.push(`Ran ${pluralize(commandCount, 'command', 'commands')}`)
  }
  if (otherToolCount > 0) {
    parts.push(`Used ${pluralize(otherToolCount, 'tool call', 'tool calls')}`)
  }

  if (parts.length === 0) {
    return `Ran ${pluralize(items.length, 'tool call', 'tool calls')}`
  }
  if (parts.length === 1) {
    return parts[0]
  }
  return [parts[0], ...parts.slice(1).map((part) => lowercaseFirst(part))].join(', ')
}

function summarizeLiveToolItems(items: SessionItem[]): string {
  if (items.length !== 1) {
    return summarizeToolItems(items)
  }

  const item = items[0]
  const payload = isRecord(item.payload) ? item.payload : {}
  const payloadType = normalizeText(payload.type)
  const kind = payloadType || item.kind

  if (kind === 'commandExecution') {
    const commandPreview = toSingleLinePreview(normalizeText(payload.command), LIVE_TOOL_PREVIEW_MAX_CHARS)
    return commandPreview ? `Ran ${commandPreview}` : 'Ran command'
  }

  const fallback = summarizeToolItems(items)
  if (fallback === 'Used 1 tool call') {
    const title = toSingleLinePreview(renderToolTitle(item), 48)
    return title ? `Used ${title}` : fallback
  }
  return fallback
}

function renderToolTitle(item: SessionItem): string {
  const itemType = payloadTypeOf(item)
  if (itemType) {
    return itemType
  }
  const itemKind = normalizedKindOf(item)
  if (itemKind) {
    return itemKind
  }
  return item.kind
}

function shouldCollapseUserMessage(text: string): boolean {
  if (!text) {
    return false
  }
  if (text.length > USER_MESSAGE_COLLAPSE_CHAR_LIMIT) {
    return true
  }
  return text.split(/\r\n|\r|\n/).length > USER_MESSAGE_COLLAPSE_LINE_LIMIT
}

function getCollapsedUserMessageText(text: string): string {
  if (!shouldCollapseUserMessage(text)) {
    return text
  }

  const lines = text.split(/\r\n|\r|\n/)
  let clipped = lines.slice(0, USER_MESSAGE_COLLAPSE_LINE_LIMIT).join('\n')
  if (clipped.length > USER_MESSAGE_COLLAPSE_CHAR_LIMIT) {
    clipped = clipped.slice(0, USER_MESSAGE_COLLAPSE_CHAR_LIMIT)
  }
  const trimmed = clipped.trimEnd()
  return `${trimmed}\n...`
}

function getActiveAgentStreamToken(
  threadId: string,
  turns: SessionTurn[],
  itemsByTurn: Record<string, SessionItem[]>,
): string | null {
  for (let turnIndex = turns.length - 1; turnIndex >= 0; turnIndex -= 1) {
    const turn = turns[turnIndex]
    const items = itemsByTurn[`${threadId}:${turn.id}`] ?? []
    for (let itemIndex = items.length - 1; itemIndex >= 0; itemIndex -= 1) {
      const item = items[itemIndex]
      if (!isAgentMessageItem(item) || item.status !== 'inProgress') {
        continue
      }
      const textLength = renderItemText(item).length
      return `${turn.id}:${item.id}:${item.updatedAtMs}:${textLength}`
    }
  }
  return null
}

function formatItemTimeLabel(timestampMs: number): string {
  const fallback = new Date()
  const value = Number.isFinite(timestampMs) ? new Date(timestampMs) : fallback
  const date = Number.isNaN(value.getTime()) ? fallback : value
  return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
}

async function copyTextToClipboard(value: string): Promise<void> {
  if (!value) {
    return
  }
  if (typeof navigator !== 'undefined' && navigator.clipboard && typeof navigator.clipboard.writeText === 'function') {
    await navigator.clipboard.writeText(value)
    return
  }
  if (typeof document === 'undefined') {
    return
  }
  const textarea = document.createElement('textarea')
  textarea.value = value
  textarea.setAttribute('readonly', 'true')
  textarea.style.position = 'fixed'
  textarea.style.left = '-9999px'
  document.body.appendChild(textarea)
  textarea.select()
  try {
    document.execCommand('copy')
  } finally {
    document.body.removeChild(textarea)
  }
}

function buildTranscriptRows(visibleRows: VisibleTranscriptRow[]): TranscriptRow[] {
  const rows: TranscriptRow[] = []
  const rowsByTurn = new Map<string, { turn: SessionTurn; items: SessionItem[] }>()
  for (const row of visibleRows) {
    const existing = rowsByTurn.get(row.turn.id)
    if (existing) {
      existing.items.push(row.item)
    } else {
      rowsByTurn.set(row.turn.id, { turn: row.turn, items: [row.item] })
    }
  }
  for (const { turn, items } of rowsByTurn.values()) {
    if (items.length === 0) {
      continue
    }
    if (!isTerminalTurn(turn)) {
      let liveToolCluster: SessionItem[] = []
      let liveToolSummaryIndex = 0
      const flushLiveToolCluster = () => {
        if (liveToolCluster.length === 0) {
          return
        }
        rows.push({
          key: `${turn.id}:live-tool-summary-${liveToolSummaryIndex}`,
          type: 'toolSummary',
          summary: summarizeLiveToolItems(liveToolCluster),
        })
        liveToolSummaryIndex += 1
        liveToolCluster = []
      }

      for (const item of items) {
        if (isContextCompactionItem(item)) {
          flushLiveToolCluster()
          rows.push({
            key: `${turn.id}:${item.id}:compact-marker`,
            type: 'compactMarker',
          })
          continue
        }
        if (isToolItem(item)) {
          liveToolCluster.push(item)
          continue
        }
        flushLiveToolCluster()
        rows.push({
          key: `${turn.id}:${item.id}`,
          type: 'item',
          item,
        })
      }
      flushLiveToolCluster()
      continue
    }

    const agentMessageIndexes: number[] = []
    for (let index = 0; index < items.length; index += 1) {
      if (isAgentMessageItem(items[index])) {
        agentMessageIndexes.push(index)
      }
    }
    const summaryAgentIndex =
      agentMessageIndexes.length > 1 ? agentMessageIndexes[agentMessageIndexes.length - 1] : -1
    const hiddenReasoningEntries: AgentWorkSummaryEntry[] = []
    let hiddenToolCluster: SessionItem[] = []
    let hiddenToolSummaryIndex = 0
    const flushHiddenToolCluster = () => {
      if (hiddenToolCluster.length === 0) {
        return
      }
      hiddenReasoningEntries.push({
        key: `${turn.id}:agent-work-tool-summary-${hiddenToolSummaryIndex}`,
        type: 'toolSummary',
        summary: summarizeToolItems(hiddenToolCluster),
      })
      hiddenToolSummaryIndex += 1
      hiddenToolCluster = []
    }

    let toolCluster: SessionItem[] = []
    let toolSummaryIndex = 0
    const flushToolCluster = () => {
      if (toolCluster.length === 0) {
        return
      }
      rows.push({
        key: `${turn.id}:tool-summary-${toolSummaryIndex}`,
        type: 'toolSummary',
        summary: summarizeToolItems(toolCluster),
      })
      toolSummaryIndex += 1
      toolCluster = []
    }

    for (let itemIndex = 0; itemIndex < items.length; itemIndex += 1) {
      const item = items[itemIndex]
      if (summaryAgentIndex >= 0 && itemIndex < summaryAgentIndex) {
        if (isContextCompactionItem(item)) {
          flushHiddenToolCluster()
          hiddenReasoningEntries.push({
            key: `${turn.id}:${item.id}:compact-marker`,
            type: 'compactMarker',
          })
          continue
        }
        if (isToolItem(item)) {
          hiddenToolCluster.push(item)
          continue
        }
        if (resolveRowVariant(item) !== 'user') {
          flushHiddenToolCluster()
          hiddenReasoningEntries.push({
            key: `${turn.id}:${item.id}`,
            type: 'item',
            item,
          })
          continue
        }
      }

      if (isContextCompactionItem(item)) {
        flushToolCluster()
        rows.push({
          key: `${turn.id}:${item.id}:compact-marker`,
          type: 'compactMarker',
        })
        continue
      }

      if (isToolItem(item)) {
        toolCluster.push(item)
        continue
      }

      flushToolCluster()
      if (summaryAgentIndex >= 0 && itemIndex === summaryAgentIndex) {
        flushHiddenToolCluster()
      }
      if (summaryAgentIndex >= 0 && itemIndex === summaryAgentIndex && hiddenReasoningEntries.length > 0) {
        rows.push({
          key: `${turn.id}:agent-work-summary`,
          type: 'agentWorkSummary',
          entries: [...hiddenReasoningEntries],
        })
      }
      rows.push({
        key: `${turn.id}:${item.id}`,
        type: 'item',
        item,
      })
    }

    flushToolCluster()
    const turnFileSummary = summarizeTurnFileChanges(items)
    if (turnFileSummary) {
      rows.push({
        key: `${turn.id}:files-changed`,
        type: 'turnFileSummary',
        summary: turnFileSummary,
      })
    }
  }
  return rows
}

function latestWorkflowContextItem(
  threadId: string,
  turns: SessionTurn[],
  itemsByTurn: Record<string, SessionItem[]>,
): SessionItem | null {
  let latest: SessionItem | null = null
  for (const turn of turns) {
    const key = `${threadId}:${turn.id}`
    for (const item of itemsByTurn[key] ?? []) {
      if (!isWorkflowContextItem(item)) {
        continue
      }
      if (!workflowContextPayload(item)) {
        continue
      }
      if (!latest || (item.updatedAtMs ?? item.createdAtMs ?? 0) >= (latest.updatedAtMs ?? latest.createdAtMs ?? 0)) {
        latest = item
      }
    }
  }
  return latest
}

export function TranscriptPanel({
  threadId,
  turns,
  itemsByTurn,
  visibleRows,
  workflowContextItem = null,
  showWorkflowContext = true,
}: TranscriptPanelProps) {
  const [expandedUserRows, setExpandedUserRows] = useState<Record<string, boolean>>({})
  const [copiedUserRow, setCopiedUserRow] = useState<string | null>(null)
  const [expandedFileRowsBySummary, setExpandedFileRowsBySummary] = useState<Record<string, string | null>>({})
  const [expandedAgentWorkRows, setExpandedAgentWorkRows] = useState<Record<string, boolean>>({})
  const transcriptRef = useRef<HTMLElement | null>(null)
  const observedThreadIdRef = useRef<string | null>(threadId)
  const activeThreadIdRef = useRef<string | null>(threadId)
  const pendingRestoreThreadIdRef = useRef<string | null>(null)
  const shouldAutoFollowRef = useRef<boolean>(true)
  const wasStreamingAgentRef = useRef<boolean>(false)
  const scrollSaveTimerRef = useRef<number | null>(null)
  const pendingScrollSaveRef = useRef<{ threadId: string; element: HTMLElement } | null>(null)

  const flushPendingScrollSave = () => {
    if (scrollSaveTimerRef.current !== null) {
      window.clearTimeout(scrollSaveTimerRef.current)
      scrollSaveTimerRef.current = null
    }
    const pending = pendingScrollSaveRef.current
    if (!pending) {
      return
    }
    rememberThreadScrollPosition(pending.threadId, pending.element)
    pendingScrollSaveRef.current = null
  }

  const scheduleScrollSave = (targetThreadId: string, element: HTMLElement) => {
    pendingScrollSaveRef.current = { threadId: targetThreadId, element }
    if (scrollSaveTimerRef.current !== null) {
      window.clearTimeout(scrollSaveTimerRef.current)
    }
    scrollSaveTimerRef.current = window.setTimeout(() => {
      const pending = pendingScrollSaveRef.current
      if (pending) {
        rememberThreadScrollPosition(pending.threadId, pending.element)
        pendingScrollSaveRef.current = null
      }
      scrollSaveTimerRef.current = null
    }, SCROLL_SNAPSHOT_DEBOUNCE_MS)
  }

  const rows = threadId ? buildTranscriptRows(visibleRows ?? []) : []
  const contextItem = showWorkflowContext
    ? workflowContextItem ?? (threadId ? latestWorkflowContextItem(threadId, turns, itemsByTurn) : null)
    : null
  const activeAgentStreamToken = threadId ? getActiveAgentStreamToken(threadId, turns, itemsByTurn) : null
  const hasActiveAgentStream = Boolean(activeAgentStreamToken)
  activeThreadIdRef.current = threadId
  if (observedThreadIdRef.current !== threadId) {
    pendingRestoreThreadIdRef.current = threadId
    observedThreadIdRef.current = threadId
  }

  useLayoutEffect(() => {
    flushPendingScrollSave()
  }, [threadId])

  useEffect(
    () => () => {
      flushPendingScrollSave()
      const currentThreadId = activeThreadIdRef.current
      const element = transcriptRef.current
      if (currentThreadId && element) {
        rememberThreadScrollPosition(currentThreadId, element)
      }
    },
    [],
  )

  useEffect(() => {
    if (!threadId) {
      wasStreamingAgentRef.current = false
      return
    }
    if (hasActiveAgentStream && !wasStreamingAgentRef.current) {
      // Start following automatically when a new agent response begins.
      shouldAutoFollowRef.current = true
    }
    wasStreamingAgentRef.current = hasActiveAgentStream
  }, [hasActiveAgentStream, threadId])

  useLayoutEffect(() => {
    if (!threadId) {
      return
    }
    if (pendingRestoreThreadIdRef.current !== threadId) {
      return
    }
    const element = transcriptRef.current
    if (!element) {
      return
    }

    const saved = threadScrollSnapshots.get(threadId)
    if (rows.length === 0 && !contextItem) {
      // Wait for the thread rows to hydrate before restoring or initializing viewport.
      return
    }
    if (!saved) {
      // New threads should start near the most recent message.
      element.scrollTop = element.scrollHeight
      rememberThreadScrollPosition(threadId, element)
      shouldAutoFollowRef.current = true
      pendingRestoreThreadIdRef.current = null
      return
    }

    const maxTop = Math.max(0, element.scrollHeight - element.clientHeight)
    const restoredFromBottom = element.scrollHeight - element.clientHeight - saved.fromBottom
    const targetTop = Number.isFinite(restoredFromBottom)
      ? Math.min(maxTop, Math.max(0, restoredFromBottom))
      : Math.min(maxTop, Math.max(0, saved.top))
    element.scrollTop = targetTop
    shouldAutoFollowRef.current = isScrollNearBottom(element)
    pendingRestoreThreadIdRef.current = null
  }, [Boolean(contextItem), rows.length, threadId])

  useLayoutEffect(() => {
    if (!threadId || !activeAgentStreamToken || !shouldAutoFollowRef.current) {
      return
    }
    const element = transcriptRef.current
    if (!element) {
      return
    }
    element.scrollTop = element.scrollHeight
    rememberThreadScrollPosition(threadId, element)
  }, [activeAgentStreamToken, threadId])

  const handleTranscriptScroll = () => {
    if (!threadId) {
      return
    }
    const element = transcriptRef.current
    if (!element) {
      return
    }
    shouldAutoFollowRef.current = isScrollNearBottom(element)
    scheduleScrollSave(threadId, element)
  }

  if (!threadId) {
    return (
      <section className="sessionV2Transcript" ref={transcriptRef}>
        {contextItem ? <WorkflowContextCard item={contextItem} sticky /> : null}
      </section>
    )
  }
  if (rows.length === 0 && !contextItem) {
    return <section className="sessionV2Transcript" ref={transcriptRef} onScroll={handleTranscriptScroll} />
  }

  return (
    <section className="sessionV2Transcript" ref={transcriptRef} onScroll={handleTranscriptScroll}>
      {contextItem ? <WorkflowContextCard item={contextItem} sticky /> : null}
      {rows.map((row) => {
        if (row.type === 'compactMarker') {
          return (
            <div key={row.key} className="sessionV2CompactMarker">
              <span className="sessionV2CompactMarkerText">Context automatically compacted</span>
            </div>
          )
        }
        if (row.type === 'agentWorkSummary') {
          const isExpanded = Boolean(expandedAgentWorkRows[row.key])
          return (
            <section key={row.key} className="sessionV2WorkSummary">
              <button
                type="button"
                className="sessionV2WorkSummaryToggle"
                aria-expanded={isExpanded}
                onClick={() => {
                  setExpandedAgentWorkRows((prev) => ({
                    ...prev,
                    [row.key]: !Boolean(prev[row.key]),
                  }))
                }}
              >
                <span className="sessionV2WorkSummaryLabel">Reasoning summary</span>
                <span
                  className={`sessionV2WorkSummaryChevron ${isExpanded ? 'sessionV2WorkSummaryChevronOpen' : ''}`}
                  aria-hidden
                >
                  &gt;
                </span>
              </button>
              {isExpanded ? (
                <div className="sessionV2WorkSummaryExpanded">
                  {row.entries.map((entry) => {
                    if (entry.type === 'compactMarker') {
                      return (
                        <div key={`${row.key}:${entry.key}`} className="sessionV2CompactMarker">
                          <span className="sessionV2CompactMarkerText">Context automatically compacted</span>
                        </div>
                      )
                    }
                    if (entry.type === 'toolSummary') {
                      return (
                        <div key={`${row.key}:${entry.key}`} className="sessionV2MessageRow sessionV2MessageRowAssistant">
                          <div className="sessionV2ToolSummary">{entry.summary}</div>
                        </div>
                      )
                    }

                    if (showWorkflowContext && isWorkflowContextItem(entry.item)) {
                      return <WorkflowContextCard key={`${row.key}:${entry.key}`} item={entry.item} />
                    }

                    const variant = resolveRowVariant(entry.item)
                    const text = renderItemText(entry.item)
                    if (variant === 'unknown') {
                      return null
                    }
                    const rowClassName =
                      variant === 'assistant'
                        ? 'sessionV2MessageRow sessionV2MessageRowAssistant'
                        : variant === 'user'
                          ? 'sessionV2MessageRow sessionV2MessageRowUser'
                          : 'sessionV2MessageRow'
                    const bubbleClassName =
                      variant === 'assistant'
                        ? 'sessionV2Bubble sessionV2BubbleAssistantInline'
                        : variant === 'user'
                          ? 'sessionV2Bubble sessionV2BubbleUser'
                          : 'sessionV2Bubble'

                    return (
                      <article key={`${row.key}:${entry.key}`} className={rowClassName}>
                        <div className={bubbleClassName}>
                          {variant === 'assistant' && text ? (
                            <SharedMarkdownRenderer content={text} variant="document" />
                          ) : (
                            <pre className="sessionV2MessageText">{text || '...'}</pre>
                          )}
                        </div>
                      </article>
                    )
                  })}
                </div>
              ) : null}
            </section>
          )
        }
        if (row.type === 'turnFileSummary') {
          const summary = row.summary
          const expandedEntryKey = expandedFileRowsBySummary[row.key] ?? null
          return (
            <article key={row.key} className="sessionV2TurnFileSummary">
              <header className="sessionV2TurnFileSummaryHeader">
                <span className="sessionV2TurnFileSummaryTitle">
                  {pluralize(summary.fileCount, 'file', 'files')} changed
                  {summary.added > 0 || summary.removed > 0 ? (
                    <span className="sessionV2TurnFileSummaryStats">
                      <span className="sessionV2TurnFileSummaryAdd">+{summary.added}</span>
                      <span className="sessionV2TurnFileSummaryDel">-{summary.removed}</span>
                    </span>
                  ) : null}
                </span>
                <button type="button" className="sessionV2TurnFileSummaryUndo" aria-label="Undo changes">
                  Undo
                </button>
              </header>
              <ul className="sessionV2TurnFileSummaryList" aria-label="Changed files">
                {summary.entries.map((entry, entryIndex) => {
                  const entryKey = `${entry.path}:${entry.changeType}:${entryIndex}`
                  const isExpanded = expandedEntryKey === entryKey
                  const diffLines = buildRenderableDiffLines(entry.diffText)
                  return (
                    <li key={`${row.key}:${entryKey}`} className="sessionV2TurnFileSummaryItem">
                      <button
                        type="button"
                        className="sessionV2TurnFileSummaryItemButton"
                        aria-expanded={isExpanded}
                        onClick={() => {
                          setExpandedFileRowsBySummary((prev) => ({
                            ...prev,
                            [row.key]: prev[row.key] === entryKey ? null : entryKey,
                          }))
                        }}
                      >
                        <div className="sessionV2TurnFileSummaryItemMain">
                          <span className="sessionV2TurnFileSummaryPath">{shortenPath(entry.path)}</span>
                        </div>
                        <div className="sessionV2TurnFileSummaryItemRight">
                          {(entry.added > 0 || entry.removed > 0) ? (
                            <span className="sessionV2TurnFileSummaryItemStats">
                              <span className="sessionV2TurnFileSummaryAdd">+{entry.added}</span>
                              <span className="sessionV2TurnFileSummaryDel">-{entry.removed}</span>
                            </span>
                          ) : null}
                          <span
                            className={`sessionV2TurnFileSummaryChevron ${isExpanded ? 'sessionV2TurnFileSummaryChevronOpen' : ''}`}
                            aria-hidden
                          >
                            <svg viewBox="0 0 20 20" focusable="false" aria-hidden>
                              <path d="M5.5 7.5L10 12l4.5-4.5" />
                            </svg>
                          </span>
                        </div>
                      </button>
                      {isExpanded ? (
                        <div className="sessionV2TurnFileSummaryDiffPanel">
                          {diffLines.length > 0 ? (
                            <div className="sessionV2TurnFileSummaryDiffViewport">
                              {diffLines.map((line, lineIndex) => {
                                const rowClassName =
                                  line.kind === 'added'
                                    ? 'sessionV2TurnFileSummaryDiffRow sessionV2TurnFileSummaryDiffRowAdd'
                                    : line.kind === 'removed'
                                      ? 'sessionV2TurnFileSummaryDiffRow sessionV2TurnFileSummaryDiffRowDel'
                                      : 'sessionV2TurnFileSummaryDiffRow sessionV2TurnFileSummaryDiffRowCtx'
                                return (
                                  <div key={`${entryKey}:diff:${lineIndex}`} className={rowClassName}>
                                    <span className="sessionV2TurnFileSummaryDiffLineNum">
                                      {line.lineNumber ?? ''}
                                    </span>
                                    <code className="sessionV2TurnFileSummaryDiffCode">
                                      {line.text ? highlightDiffCodeLine(line.text, `${entryKey}:code:${lineIndex}`) : ' '}
                                    </code>
                                  </div>
                                )
                              })}
                            </div>
                          ) : entry.summary ? (
                            <div className="sessionV2TurnFileSummaryItemHint">{entry.summary}</div>
                          ) : (
                            <div className="sessionV2TurnFileSummaryItemHint">No diff excerpt for this file.</div>
                          )}
                        </div>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            </article>
          )
        }
        if (row.type === 'toolSummary') {
          return (
            <div key={row.key} className="sessionV2MessageRow sessionV2MessageRowAssistant">
              <div className="sessionV2ToolSummary">{row.summary}</div>
            </div>
          )
        }

        if (showWorkflowContext && isWorkflowContextItem(row.item)) {
          return <WorkflowContextCard key={row.key} item={row.item} />
        }

        const variant = resolveRowVariant(row.item)
        const text = renderItemText(row.item)
        if (variant === 'unknown') {
          return null
        }
        if (variant === 'tool') {
          return (
            <article key={row.key} className="sessionV2ToolCard">
              <header className="sessionV2ToolCardHeader">
                <span>{renderToolTitle(row.item)}</span>
                <small>{row.item.status}</small>
              </header>
              <pre className="sessionV2ToolCardText">{text || '(no output yet)'}</pre>
            </article>
          )
        }

        const rowClassName =
          variant === 'user'
            ? 'sessionV2MessageRow sessionV2MessageRowUser'
            : variant === 'assistant'
              ? 'sessionV2MessageRow sessionV2MessageRowAssistant'
              : 'sessionV2MessageRow'
        const bubbleClassName =
          variant === 'user'
            ? 'sessionV2Bubble sessionV2BubbleUser'
            : variant === 'assistant'
              ? 'sessionV2Bubble sessionV2BubbleAssistantInline'
              : 'sessionV2Bubble'
        const isUserMessage = variant === 'user'
        const canCollapseUserMessage = isUserMessage && shouldCollapseUserMessage(text)
        const isExpanded = isUserMessage && Boolean(expandedUserRows[row.key])
        const messageText = canCollapseUserMessage && !isExpanded ? getCollapsedUserMessageText(text) : text
        const timeLabel = isUserMessage ? formatItemTimeLabel(row.item.createdAtMs) : ''

        const handleToggleUserMessage = () => {
          if (!canCollapseUserMessage) {
            return
          }
          setExpandedUserRows((prev) => ({
            ...prev,
            [row.key]: !Boolean(prev[row.key]),
          }))
        }

        const handleCopyUserMessage = async () => {
          if (!isUserMessage || !text) {
            return
          }
          try {
            await copyTextToClipboard(text)
            setCopiedUserRow(row.key)
            window.setTimeout(() => {
              setCopiedUserRow((current) => (current === row.key ? null : current))
            }, 1400)
          } catch {
            // ignore clipboard failures for non-secure contexts
          }
        }

        return (
          <article key={row.key} className={rowClassName}>
            <div className={bubbleClassName}>
              {variant === 'assistant' && messageText ? (
                <SharedMarkdownRenderer content={messageText} variant="document" />
              ) : (
                <pre className="sessionV2MessageText">{messageText || '...'}</pre>
              )}
              {canCollapseUserMessage ? (
                <button
                  type="button"
                  className="sessionV2UserMessageToggle"
                  onClick={handleToggleUserMessage}
                  aria-expanded={isExpanded}
                >
                  {isExpanded ? 'Show less' : 'Show more'}
                </button>
              ) : null}
            </div>
            {isUserMessage ? (
              <div className="sessionV2UserMeta" aria-label="User message details">
                <span className="sessionV2UserMetaTime">{timeLabel}</span>
                <button
                  type="button"
                  className="sessionV2UserMetaCopy"
                  onClick={() => {
                    void handleCopyUserMessage()
                  }}
                  aria-label="Copy message"
                  title="Copy message"
                >
                  {copiedUserRow === row.key ? (
                    <span className="sessionV2UserMetaCopiedLabel">Copied</span>
                  ) : (
                    <svg viewBox="0 0 24 24" width={15} height={15} fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                  )}
                </button>
              </div>
            ) : null}
          </article>
        )
      })}
    </section>
  )
}
