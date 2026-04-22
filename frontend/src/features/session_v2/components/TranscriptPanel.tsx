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

type FileChangeStats = {
  created: number
  edited: number
  deleted: number
  renamed: number
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object'
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
  }
  return rows
}

export function TranscriptPanel({ threadId, turns, itemsByTurn }: TranscriptPanelProps) {
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

        return (
          <article
            key={row.key}
            className={variant === 'user' ? 'sessionV2MessageRow sessionV2MessageRowUser' : 'sessionV2MessageRow'}
          >
            <div className={variant === 'user' ? 'sessionV2Bubble sessionV2BubbleUser' : 'sessionV2Bubble'}>
              <pre className="sessionV2MessageText">{text || '...'}</pre>
            </div>
          </article>
        )
      })}
    </section>
  )
}
