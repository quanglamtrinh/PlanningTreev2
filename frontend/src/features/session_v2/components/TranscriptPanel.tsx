import { useState } from 'react'
import { SharedMarkdownRenderer } from '../../markdown/SharedMarkdownRenderer'
import type { SessionItem, SessionTurn } from '../contracts'

type TranscriptPanelProps = {
  threadId: string | null
  turns: SessionTurn[]
  itemsByTurn: Record<string, SessionItem[]>
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
}

type TurnFileSummary = {
  fileCount: number
  added: number
  removed: number
  entries: TurnFileChangeEntry[]
}

const USER_MESSAGE_COLLAPSE_CHAR_LIMIT = 1100
const USER_MESSAGE_COLLAPSE_LINE_LIMIT = 14

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

function pluralize(count: number, singular: string, plural: string): string {
  return `${count} ${count === 1 ? singular : plural}`
}

function lowercaseFirst(text: string): string {
  if (!text) {
    return ''
  }
  return `${text.charAt(0).toLowerCase()}${text.slice(1)}`
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
    if (type === 'text') {
      const text = normalizeText(entry.text)
      if (text) {
        rows.push(text)
      }
      continue
    }
    if (type === 'image') {
      const imageUrl = normalizeText(entry.imageUrl)
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

function renderItemText(item: SessionItem): string {
  const payload = isRecord(item.payload) ? item.payload : {}
  const itemType = normalizeText(payload.type)

  if (itemType === 'userMessage') {
    const text = extractUserContent(payload.content)
    return text || normalizeText(payload.text)
  }
  if (itemType === 'agentMessage' || itemType === 'plan') {
    return normalizeText(payload.text) || normalizeText(payload.delta)
  }
  if (itemType === 'reasoning') {
    return extractReasoningContent(payload)
  }
  if (itemType === 'commandExecution') {
    const aggregated = normalizeText(payload.aggregatedOutput || payload.output)
    if (aggregated) {
      return aggregated
    }
    return normalizeText(payload.command)
  }
  if (itemType === 'fileChange') {
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
  if (item.kind === 'reasoning') {
    const reasoning = extractReasoningContent(payload)
    if (reasoning) {
      return reasoning
    }
  }
  if (item.kind === 'fileChange') {
    const changes = extractFileChanges(payload)
    if (changes) {
      return changes
    }
  }

  return formatPayloadFallback(payload)
}

function resolveRowVariant(item: SessionItem): 'user' | 'assistant' | 'tool' {
  const itemType = payloadTypeOf(item)
  if (item.kind === 'userMessage' || itemType === 'userMessage') {
    return 'user'
  }
  if (
    item.kind === 'agentMessage' ||
    item.kind === 'plan' ||
    item.kind === 'reasoning' ||
    itemType === 'agentMessage' ||
    itemType === 'plan' ||
    itemType === 'reasoning'
  ) {
    return 'assistant'
  }
  return 'tool'
}

function isContextCompactionItem(item: SessionItem): boolean {
  return payloadTypeOf(item) === 'contextCompaction'
}

function isToolItem(item: SessionItem): boolean {
  return !isContextCompactionItem(item) && resolveRowVariant(item) === 'tool'
}

function isFileChangeItem(item: SessionItem): boolean {
  return payloadTypeOf(item) === 'fileChange' || item.kind === 'fileChange'
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

function renderToolTitle(item: SessionItem): string {
  const itemType = payloadTypeOf(item)
  if (itemType) {
    return itemType
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

function buildTranscriptRows(
  threadId: string,
  turns: SessionTurn[],
  itemsByTurn: Record<string, SessionItem[]>,
): TranscriptRow[] {
  const rows: TranscriptRow[] = []
  for (const turn of turns) {
    const key = `${threadId}:${turn.id}`
    const items = itemsByTurn[key] ?? []
    if (!isTerminalTurn(turn)) {
      for (const item of items) {
        if (isContextCompactionItem(item)) {
          rows.push({
            key: `${turn.id}:${item.id}:compact-marker`,
            type: 'compactMarker',
          })
          continue
        }
        rows.push({
          key: `${turn.id}:${item.id}`,
          type: 'item',
          item,
        })
      }
      continue
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

    for (const item of items) {
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

export function TranscriptPanel({ threadId, turns, itemsByTurn }: TranscriptPanelProps) {
  const [expandedUserRows, setExpandedUserRows] = useState<Record<string, boolean>>({})
  const [copiedUserRow, setCopiedUserRow] = useState<string | null>(null)

  if (!threadId) {
    return (
      <section className="sessionV2Transcript">
        <div className="sessionV2Empty">No active thread</div>
      </section>
    )
  }

  const rows = buildTranscriptRows(threadId, turns, itemsByTurn)
  if (rows.length === 0) {
    return (
      <section className="sessionV2Transcript">
        <div className="sessionV2Empty">No messages yet.</div>
      </section>
    )
  }

  return (
    <section className="sessionV2Transcript">
      {rows.map((row) => {
        if (row.type === 'compactMarker') {
          return (
            <div key={row.key} className="sessionV2CompactMarker">
              <span className="sessionV2CompactMarkerText">Context automatically compacted</span>
            </div>
          )
        }
        if (row.type === 'turnFileSummary') {
          const summary = row.summary
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
                  Undo ↺
                </button>
              </header>
              <ul className="sessionV2TurnFileSummaryList" aria-label="Changed files">
                {summary.entries.map((entry) => (
                  <li key={`${row.key}:${entry.path}`} className="sessionV2TurnFileSummaryItem">
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
                      <span className="sessionV2TurnFileSummaryChevron" aria-hidden>∨</span>
                    </div>
                    {entry.summary ? (
                      <div className="sessionV2TurnFileSummaryItemHint">{entry.summary}</div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </article>
          )
        }
        if (row.type === 'toolSummary') {
          return (
            <div key={row.key} className="sessionV2ToolSummary">
              {row.summary}
            </div>
          )
        }

        const variant = resolveRowVariant(row.item)
        const text = renderItemText(row.item)
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
              {variant === 'assistant' && text ? (
                <SharedMarkdownRenderer content={text} variant="document" />
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
