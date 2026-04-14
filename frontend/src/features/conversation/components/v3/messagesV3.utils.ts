import type {
  ConversationItemV3,
  ReasoningItemV3,
  ThreadSnapshotV3,
} from '../../../../api/types'
import {
  buildParseCacheKey,
  PARSE_CACHE_RENDERER_VERSION,
} from './parseCacheContract'
import {
  buildParseArtifactVariantKey,
  readOrComputeParseArtifact,
} from './parseArtifactCache'

export type ReasoningPresentationMetaV3 = {
  hasBody: boolean
  visibleSummary: string
  visibleDetail: string | null
  workingLabel: string | null
}

export type VisibleMessageStateV3 = {
  visibleItems: ConversationItemV3[]
  reasoningMetaById: Map<string, ReasoningPresentationMetaV3>
}

export type ToolGroupEntryV3 =
  | {
      kind: 'item'
      item: ConversationItemV3
    }
  | {
      kind: 'toolGroup'
      group: {
        id: string
        items: ConversationItemV3[]
        toolCount: number
        supportingItemCount: number
      }
    }

function normalizeBlockText(text: string | null | undefined): string {
  return String(text ?? '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .trim()
}

function normalizeWorkingLabelLine(line: string): string {
  return line
    .replace(/^\s*(?:[#>*+-]+|\d+[.)])\s*/, '')
    .replace(/\s+/g, ' ')
    .trim()
}

function toWorkingLabel(summaryText: string): string | null {
  const lines = summaryText
    .split('\n')
    .map((line) => normalizeWorkingLabelLine(line))
    .filter(Boolean)
  if (!lines.length) {
    return null
  }
  const label = lines[0]
  return label.length > 80 ? `${label.slice(0, 77).trimEnd()}...` : label
}

export function getReasoningPresentationMetaV3(item: ReasoningItemV3): ReasoningPresentationMetaV3 {
  const summaryKey = buildParseCacheKey({
    threadId: item.threadId,
    itemId: item.id,
    updatedAt: item.updatedAt,
    mode: 'reasoning_summary',
    rendererVersion: PARSE_CACHE_RENDERER_VERSION,
  })
  const detailKey = buildParseCacheKey({
    threadId: item.threadId,
    itemId: item.id,
    updatedAt: item.updatedAt,
    mode: 'reasoning_detail',
    rendererVersion: PARSE_CACHE_RENDERER_VERSION,
  })

  const visibleSummary = readOrComputeParseArtifact<string>(
    buildParseArtifactVariantKey(summaryKey, 'normalized_text'),
    () => normalizeBlockText(item.summaryText),
  ).value
  const detail = readOrComputeParseArtifact<string>(
    buildParseArtifactVariantKey(detailKey, 'normalized_text'),
    () => normalizeBlockText(item.detailText),
  ).value
  const workingLabel = readOrComputeParseArtifact<string | null>(
    buildParseArtifactVariantKey(summaryKey, 'working_label'),
    () => toWorkingLabel(visibleSummary),
  ).value

  return readOrComputeParseArtifact<ReasoningPresentationMetaV3>(
    `${buildParseArtifactVariantKey(summaryKey, 'presentation_meta')}|detail_key=${encodeURIComponent(detailKey)}`,
    () => ({
      hasBody: visibleSummary.length > 0 || detail.length > 0,
      visibleSummary,
      visibleDetail: detail || null,
      workingLabel,
    }),
  ).value
}

function isVisibleConversationItemV3(
  item: ConversationItemV3,
  reasoningMetaById: Map<string, ReasoningPresentationMetaV3>,
): boolean {
  if (item.kind === 'reasoning') {
    return reasoningMetaById.get(item.id)?.hasBody ?? false
  }
  if (item.kind === 'message') {
    return normalizeBlockText(item.text).length > 0
  }
  return true
}

export function deriveVisibleMessageStateV3(snapshot: ThreadSnapshotV3 | null): VisibleMessageStateV3 {
  const items = snapshot?.items ?? []
  const reasoningMetaById = new Map<string, ReasoningPresentationMetaV3>()
  items.forEach((item) => {
    if (item.kind === 'reasoning') {
      reasoningMetaById.set(item.id, getReasoningPresentationMetaV3(item))
    }
  })
  const visibleItems = items.filter((item) => isVisibleConversationItemV3(item, reasoningMetaById))
  return { visibleItems, reasoningMetaById }
}

function isGroupableItemV3(item: ConversationItemV3): boolean {
  return item.kind === 'tool' || item.kind === 'reasoning' || item.kind === 'review' || item.kind === 'diff'
}

export function buildToolGroupsV3(items: ConversationItemV3[]): ToolGroupEntryV3[] {
  const entries: ToolGroupEntryV3[] = []
  let buffer: ConversationItemV3[] = []

  const flush = () => {
    if (!buffer.length) {
      return
    }
    const toolCount = buffer.filter((item) => item.kind === 'tool').length
    if (toolCount === 0 || buffer.length === 1) {
      buffer.forEach((item) => entries.push({ kind: 'item', item }))
    } else {
      entries.push({
        kind: 'toolGroup',
        group: {
          id: buffer[0].id,
          items: [...buffer],
          toolCount,
          supportingItemCount: buffer.filter((item) => item.kind !== 'tool').length,
        },
      })
    }
    buffer = []
  }

  items.forEach((item) => {
    if (isGroupableItemV3(item)) {
      buffer.push(item)
      return
    }
    flush()
    entries.push({ kind: 'item', item })
  })
  flush()

  return entries
}
