import { useCallback, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type {
  ConversationItemV3,
  PendingUserInputRequestV3,
  ProcessingState,
  ThreadSnapshotV3,
  UserInputAnswerV3,
} from '../../../../api/types'
import styles from '../ConversationFeed.module.css'
import { ConversationMarkdown } from '../ConversationMarkdown'
import { WorkingIndicator } from '../WorkingIndicator'
import {
  buildToolGroupsV3,
  deriveVisibleMessageStateV3,
  type ReasoningPresentationMetaV3,
  type ToolGroupEntryV3,
} from './messagesV3.utils'

const SCROLL_THRESHOLD_PX = 120

function pendingRequestByItemId(
  pendingRequests: PendingUserInputRequestV3[],
): Record<string, PendingUserInputRequestV3> {
  return pendingRequests.reduce<Record<string, PendingUserInputRequestV3>>((acc, request) => {
    acc[request.itemId] = request
    return acc
  }, {})
}

function normalizeText(value: string | null | undefined): string {
  return String(value ?? '').trim()
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
      <div className={`${styles.messageShell} ${item.role === 'user' ? styles.messageShellUser : styles.messageShellAssistant}`}>
        <div className={`${styles.messageBubble} ${bubbleClass}`}>
          <ConversationMarkdown content={item.text} />
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
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-reasoning">
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>Reasoning</div>
            <h3 className={styles.cardTitle}>{meta?.workingLabel ?? 'Reasoning update'}</h3>
          </div>
          {meta?.visibleDetail ? (
            <button type="button" className={styles.inlineToggle} onClick={() => onToggle(item.id)}>
              {isExpanded ? 'Collapse' : 'Expand'}
            </button>
          ) : null}
        </div>
        {meta?.visibleSummary ? <div className={styles.subtleText}>{meta.visibleSummary}</div> : null}
        {isExpanded && meta?.visibleDetail ? <pre className={styles.plainPre}>{meta.visibleDetail}</pre> : null}
      </div>
    </article>
  )
}

function ToolRowV3({
  item,
  isExpanded,
  onToggle,
}: {
  item: Extract<ConversationItemV3, { kind: 'tool' }>
  isExpanded: boolean
  onToggle: (itemId: string) => void
}) {
  const headline = normalizeText(item.title) || normalizeText(item.toolName) || 'Tool call'
  const hasBody = Boolean(normalizeText(item.argumentsText) || normalizeText(item.outputText) || item.outputFiles.length)
  const showBody = !hasBody || isExpanded

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-tool">
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>Tool</div>
            <h3 className={styles.cardTitle}>{headline}</h3>
          </div>
          {hasBody ? (
            <button type="button" className={styles.inlineToggle} onClick={() => onToggle(item.id)}>
              {showBody ? 'Collapse' : 'Expand'}
            </button>
          ) : null}
        </div>
        <div className={styles.cardMeta}>
          <span className={styles.statusPill}>{item.status}</span>
          {item.exitCode != null ? <span>exit {item.exitCode}</span> : null}
        </div>
        {showBody && normalizeText(item.argumentsText) ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Arguments</div>
            <pre className={styles.plainPre}>{item.argumentsText}</pre>
          </div>
        ) : null}
        {showBody && normalizeText(item.outputText) ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Output</div>
            <pre className={styles.plainPre}>{item.outputText}</pre>
          </div>
        ) : null}
      </div>
    </article>
  )
}

function UserInputRowV3({
  item,
  pendingRequest,
}: {
  item: Extract<ConversationItemV3, { kind: 'userInput' }>
  pendingRequest?: PendingUserInputRequestV3
}) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-v3-item-userInput">
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>User Input</div>
            <h3 className={styles.cardTitle}>{item.title ?? 'Input request'}</h3>
          </div>
          <span className={styles.statusPill}>{pendingRequest?.status ?? item.status}</span>
        </div>
        {item.questions.length ? (
          <div className={styles.subtleText}>{item.questions.length} questions requested.</div>
        ) : null}
        {item.answers.length ? (
          <div className={styles.subtleText}>{item.answers.length} answers recorded.</div>
        ) : null}
      </div>
    </article>
  )
}

function GenericCardRowV3({
  item,
  title,
  body,
}: {
  item: ConversationItemV3
  title: string
  body: ReactNode
}) {
  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid={`conversation-v3-item-${item.kind}`}>
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>{item.kind}</div>
            <h3 className={styles.cardTitle}>{title}</h3>
          </div>
          <span className={styles.statusPill}>{item.status}</span>
        </div>
        {body}
      </div>
    </article>
  )
}

function renderItemRowV3({
  item,
  pendingRequest,
  reasoningMeta,
  expandedItemIds,
  onToggleExpanded,
  onResolveUserInput,
}: {
  item: ConversationItemV3
  pendingRequest?: PendingUserInputRequestV3
  reasoningMeta?: ReasoningPresentationMetaV3
  expandedItemIds: Set<string>
  onToggleExpanded: (itemId: string) => void
  onResolveUserInput: (requestId: string, answers: UserInputAnswerV3[]) => Promise<void> | void
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
      />
    )
  }
  if (item.kind === 'userInput') {
    void onResolveUserInput
    return <UserInputRowV3 item={item} pendingRequest={pendingRequest} />
  }
  if (item.kind === 'review') {
    return (
      <GenericCardRowV3
        item={item}
        title={item.title ?? 'Review summary'}
        body={<ConversationMarkdown content={item.text} />}
      />
    )
  }
  if (item.kind === 'diff') {
    return (
      <GenericCardRowV3
        item={item}
        title={item.title ?? 'Diff'}
        body={<div className={styles.subtleText}>{item.files.length} files</div>}
      />
    )
  }
  if (item.kind === 'explore') {
    return (
      <GenericCardRowV3
        item={item}
        title={item.title ?? 'Explore'}
        body={<ConversationMarkdown content={item.text} />}
      />
    )
  }
  if (item.kind === 'status') {
    return (
      <GenericCardRowV3
        item={item}
        title={item.label || item.code || 'Status'}
        body={item.detail ? <div className={styles.subtleText}>{item.detail}</div> : null}
      />
    )
  }
  return (
    <GenericCardRowV3
      item={item}
      title={item.title || item.code || 'Error'}
      body={<div className={styles.subtleText}>{item.message}</div>}
    />
  )
}

export function MessagesV3({
  snapshot,
  isLoading,
  prefix,
  suffix,
  onResolveUserInput,
  lastCompletedAt,
  lastDurationMs,
}: {
  snapshot: ThreadSnapshotV3 | null
  isLoading: boolean
  prefix?: ReactNode
  suffix?: ReactNode
  onResolveUserInput: (requestId: string, answers: UserInputAnswerV3[]) => Promise<void> | void
  lastCompletedAt?: number | null
  lastDurationMs?: number | null
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)
  const autoScrollRef = useRef(true)
  const [expandedItemIds, setExpandedItemIds] = useState<Set<string>>(new Set())
  const [collapsedToolGroupIds, setCollapsedToolGroupIds] = useState<Set<string>>(new Set())

  const requestMap = useMemo(
    () => pendingRequestByItemId(snapshot?.uiSignals.activeUserInputRequests ?? []),
    [snapshot?.uiSignals.activeUserInputRequests],
  )

  const visibleState = useMemo(() => deriveVisibleMessageStateV3(snapshot), [snapshot])
  const groupedEntries = useMemo(
    () => buildToolGroupsV3(visibleState.visibleItems),
    [visibleState.visibleItems],
  )

  const isNearBottom = useCallback((node: HTMLDivElement) => {
    return node.scrollHeight - node.scrollTop - node.clientHeight <= SCROLL_THRESHOLD_PX
  }, [])

  const updateAutoScroll = useCallback(() => {
    if (!containerRef.current) {
      return
    }
    autoScrollRef.current = isNearBottom(containerRef.current)
  }, [isNearBottom])

  useLayoutEffect(() => {
    setExpandedItemIds(new Set())
    setCollapsedToolGroupIds(new Set())
    autoScrollRef.current = true
  }, [snapshot?.threadId])

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
  }, [groupedEntries, isNearBottom, snapshot?.activeTurnId, snapshot?.processingState, snapshot?.updatedAt])

  const toggleExpanded = useCallback((itemId: string) => {
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

  const renderGroupedEntry = useCallback(
    (entry: ToolGroupEntryV3) => {
      if (entry.kind === 'item') {
        const reasoningMeta =
          entry.item.kind === 'reasoning'
            ? visibleState.reasoningMetaById.get(entry.item.id)
            : undefined
        return (
          <div key={entry.item.id}>
            {renderItemRowV3({
              item: entry.item,
              pendingRequest: requestMap[entry.item.id],
              reasoningMeta,
              expandedItemIds,
              onToggleExpanded: toggleExpanded,
              onResolveUserInput,
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
                    <div key={item.id}>
                      {renderItemRowV3({
                        item,
                        pendingRequest: requestMap[item.id],
                        reasoningMeta,
                        expandedItemIds,
                        onToggleExpanded: toggleExpanded,
                        onResolveUserInput,
                      })}
                    </div>
                  )
                })}
              </div>
            ) : null}
          </div>
        </section>
      )
    },
    [
      collapsedToolGroupIds,
      expandedItemIds,
      onResolveUserInput,
      requestMap,
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
      {groupedEntries.length === 0 && !isLoading ? (
        <div className={styles.empty}>No conversation items yet.</div>
      ) : null}
      {groupedEntries.map(renderGroupedEntry)}
      {snapshot ? (
        <WorkingIndicator
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
