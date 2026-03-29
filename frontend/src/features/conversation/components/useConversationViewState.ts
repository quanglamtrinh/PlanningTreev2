import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { ConversationItem, ProcessingState, ReasoningItem, ToolItem } from '../../../api/types'
import { getToolHeadline } from './toolPresentation'

export const SCROLL_THRESHOLD_PX = 120
export const MAX_COMMAND_OUTPUT_LINES = 200

const LARGE_COMMAND_OUTPUT_CHAR_THRESHOLD = 600
const LARGE_COMMAND_OUTPUT_LINE_THRESHOLD = 12

type GroupableConversationItem = Extract<ConversationItem, { kind: 'tool' | 'reasoning' | 'plan' }>

export type ReasoningPresentationMeta = {
  hasBody: boolean
  visibleSummary: string
  visibleDetail: string | null
  workingLabel: string | null
}

export type ConversationListEntry =
  | {
      kind: 'item'
      item: ConversationItem
    }
  | {
      kind: 'toolGroup'
      group: {
        id: string
        items: GroupableConversationItem[]
        toolCount: number
        supportingItemCount: number
      }
    }

function normalizeBlockText(text: string | null | undefined): string {
  return String(text ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
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

export function getReasoningPresentationMeta(item: ReasoningItem): ReasoningPresentationMeta {
  const visibleSummary = normalizeBlockText(item.summaryText)
  const detail = normalizeBlockText(item.detailText)
  return {
    hasBody: visibleSummary.length > 0 || detail.length > 0,
    visibleSummary,
    visibleDetail: detail || null,
    workingLabel: toWorkingLabel(visibleSummary),
  }
}

function isGroupableItem(item: ConversationItem): item is GroupableConversationItem {
  return item.kind === 'tool' || item.kind === 'reasoning' || item.kind === 'plan'
}

function isLargeCommandOutput(item: ToolItem): boolean {
  const output = item.outputText.trim()
  if (!output) {
    return false
  }
  const lineCount = output.split('\n').length
  return output.length >= LARGE_COMMAND_OUTPUT_CHAR_THRESHOLD || lineCount >= LARGE_COMMAND_OUTPUT_LINE_THRESHOLD
}

function getPlanWorkingLabel(item: Extract<ConversationItem, { kind: 'plan' }>): string | null {
  const title = normalizeBlockText(item.title)
  if (title) {
    return title
  }
  const text = normalizeBlockText(item.text)
  if (!text) {
    return null
  }
  const firstLine = text.split('\n').map((line) => line.trim()).find(Boolean)
  if (!firstLine) {
    return null
  }
  return firstLine.length > 80 ? `${firstLine.slice(0, 77).trimEnd()}...` : firstLine
}

function isVisibleConversationItem(
  item: ConversationItem,
  reasoningMetaById: Map<string, ReasoningPresentationMeta>,
): boolean {
  if (item.kind === 'reasoning') {
    return reasoningMetaById.get(item.id)?.hasBody ?? false
  }
  if (item.kind === 'message') {
    return normalizeBlockText(item.text).length > 0
  }
  return true
}

export function buildGroupedEntries(items: ConversationItem[]): ConversationListEntry[] {
  const entries: ConversationListEntry[] = []
  let buffer: GroupableConversationItem[] = []

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
    if (isGroupableItem(item)) {
      buffer.push(item)
      return
    }
    flush()
    entries.push({ kind: 'item', item })
  })
  flush()

  return entries
}

export function useConversationViewState({
  items,
  threadId,
  processingState,
  activeTurnId,
}: {
  items: ConversationItem[]
  threadId: string | null
  processingState: ProcessingState
  activeTurnId: string | null
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const autoScrollRef = useRef(true)
  const manuallyToggledExpandedRef = useRef<Set<string>>(new Set())
  const manuallyToggledGroupsRef = useRef<Set<string>>(new Set())

  const [expandedItemIds, setExpandedItemIds] = useState<Set<string>>(new Set())
  const [collapsedToolGroupIds, setCollapsedToolGroupIds] = useState<Set<string>>(new Set())

  const isNearBottom = useCallback((node: HTMLDivElement) => {
    return node.scrollHeight - node.scrollTop - node.clientHeight <= SCROLL_THRESHOLD_PX
  }, [])

  const updateAutoScroll = useCallback(() => {
    if (!containerRef.current) {
      return
    }
    autoScrollRef.current = isNearBottom(containerRef.current)
  }, [isNearBottom])

  const requestAutoScroll = useCallback(() => {
    const container = containerRef.current
    const shouldScroll =
      autoScrollRef.current || (container ? isNearBottom(container) : true)
    if (!shouldScroll) {
      return
    }
    if (container) {
      container.scrollTop = container.scrollHeight
      return
    }
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [isNearBottom])

  useLayoutEffect(() => {
    autoScrollRef.current = true
    manuallyToggledExpandedRef.current = new Set()
    manuallyToggledGroupsRef.current = new Set()
    setExpandedItemIds(new Set())
    setCollapsedToolGroupIds(new Set())
  }, [threadId])

  const reasoningMetaById = useMemo(() => {
    const meta = new Map<string, ReasoningPresentationMeta>()
    items.forEach((item) => {
      if (item.kind === 'reasoning') {
        meta.set(item.id, getReasoningPresentationMeta(item))
      }
    })
    return meta
  }, [items])

  const visibleItems = useMemo(
    () => items.filter((item) => isVisibleConversationItem(item, reasoningMetaById)),
    [items, reasoningMetaById],
  )

  const groupedEntries = useMemo(() => buildGroupedEntries(visibleItems), [visibleItems])

  const latestReasoningLabel = useMemo(() => {
    for (let index = visibleItems.length - 1; index >= 0; index -= 1) {
      const item = visibleItems[index]
      if (item.kind === 'reasoning' && item.status === 'in_progress') {
        const label = reasoningMetaById.get(item.id)?.workingLabel
        if (label) {
          return label
        }
      }
      if (item.kind === 'tool' && item.status === 'in_progress') {
        return getToolHeadline(item)
      }
      if (item.kind === 'plan' && item.status === 'in_progress') {
        const label = getPlanWorkingLabel(item)
        if (label) {
          return label
        }
      }
    }
    return null
  }, [reasoningMetaById, visibleItems])

  const scrollKey = useMemo(
    () =>
      visibleItems
        .map((item) => `${item.id}:${item.updatedAt}:${item.status}`)
        .join('|'),
    [visibleItems],
  )

  useLayoutEffect(() => {
    const container = containerRef.current
    const shouldScroll =
      autoScrollRef.current || (container ? isNearBottom(container) : true)
    if (!shouldScroll) {
      return
    }
    if (container) {
      container.scrollTop = container.scrollHeight
      return
    }
    bottomRef.current?.scrollIntoView({ block: 'end' })
  }, [activeTurnId, isNearBottom, processingState, scrollKey, threadId])

  useEffect(() => {
    setExpandedItemIds((previous) => {
      const next = new Set(previous)
      let changed = false

      visibleItems.forEach((item) => {
        if (manuallyToggledExpandedRef.current.has(item.id)) {
          return
        }
        if (item.kind === 'tool') {
          const shouldExpand =
            item.status === 'in_progress' ||
            (item.toolType === 'commandExecution' && isLargeCommandOutput(item))
          if (shouldExpand && !next.has(item.id)) {
            next.add(item.id)
            changed = true
          } else if (!shouldExpand && next.has(item.id)) {
            next.delete(item.id)
            changed = true
          }
          return
        }
        if (item.kind === 'reasoning') {
          const shouldExpand =
            item.status === 'in_progress' &&
            Boolean(reasoningMetaById.get(item.id)?.visibleDetail)
          if (shouldExpand && !next.has(item.id)) {
            next.add(item.id)
            changed = true
          } else if (!shouldExpand && next.has(item.id)) {
            next.delete(item.id)
            changed = true
          }
        }
      })

      return changed ? next : previous
    })
  }, [reasoningMetaById, visibleItems])

  useEffect(() => {
    const visibleGroupIds = new Set(
      groupedEntries.filter((entry) => entry.kind === 'toolGroup').map((entry) => entry.group.id),
    )
    setCollapsedToolGroupIds((previous) => {
      const next = new Set([...previous].filter((id) => visibleGroupIds.has(id)))
      const unchanged =
        next.size === previous.size && [...next].every((id) => previous.has(id))
      return unchanged ? previous : next
    })
  }, [groupedEntries])

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

  return {
    containerRef,
    bottomRef,
    updateAutoScroll,
    requestAutoScroll,
    expandedItemIds,
    collapsedToolGroupIds,
    toggleExpanded,
    toggleToolGroup,
    groupedEntries,
    latestReasoningLabel,
    reasoningMetaById,
    visibleItems,
  }
}
