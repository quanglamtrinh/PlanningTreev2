import { useMemo } from 'react'
import type {
  PendingUserInputRequest,
  ProcessingState,
  ThreadSnapshotV2,
  UserInputAnswer,
} from '../../../api/types'
import { ItemRow } from './ItemRow'
import styles from './ConversationFeed.module.css'
import { useConversationViewState } from './useConversationViewState'
import { WorkingIndicator } from './WorkingIndicator'

function pendingRequestByItemId(
  pendingRequests: PendingUserInputRequest[],
): Record<string, PendingUserInputRequest> {
  return pendingRequests.reduce<Record<string, PendingUserInputRequest>>((acc, request) => {
    acc[request.itemId] = request
    return acc
  }, {})
}

export function ConversationFeed({
  snapshot,
  isLoading,
  prefix,
  onResolveUserInput,
  processingStartedAt,
  lastCompletedAt,
  lastDurationMs,
}: {
  snapshot: ThreadSnapshotV2 | null
  isLoading: boolean
  prefix?: React.ReactNode
  onResolveUserInput: (requestId: string, answers: UserInputAnswer[]) => Promise<void> | void
  processingStartedAt?: number | null
  lastCompletedAt?: number | null
  lastDurationMs?: number | null
}) {
  const items = snapshot?.items ?? []
  const requestMap = useMemo(
    () => pendingRequestByItemId(snapshot?.pendingRequests ?? []),
    [snapshot?.pendingRequests],
  )
  const {
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
  } = useConversationViewState({
    items,
    threadId: snapshot?.threadId ?? null,
    processingState: (snapshot?.processingState as ProcessingState | undefined) ?? 'idle',
    activeTurnId: snapshot?.activeTurnId ?? null,
  })

  return (
    <div
      ref={containerRef}
      className={styles.feed}
      data-testid="conversation-feed"
      onScroll={updateAutoScroll}
    >
      {prefix}
      {groupedEntries.length === 0 && !isLoading ? (
        <div className={styles.empty}>No conversation items yet.</div>
      ) : null}
      {groupedEntries.map((entry) => {
        if (entry.kind === 'item') {
          const reasoningMeta =
            entry.item.kind === 'reasoning' ? reasoningMetaById.get(entry.item.id) : undefined
          return (
            <ItemRow
              key={entry.item.id}
              item={entry.item}
              pendingRequest={requestMap[entry.item.id]}
              onResolveUserInput={onResolveUserInput}
              isExpanded={expandedItemIds.has(entry.item.id)}
              onToggleExpanded={toggleExpanded}
              onRequestAutoScroll={requestAutoScroll}
              reasoningMeta={reasoningMeta}
            />
          )
        }

        const isCollapsed = collapsedToolGroupIds.has(entry.group.id)
        const leadTool = entry.group.items.find((item) => item.kind === 'tool')
        const groupTitle =
          leadTool?.title?.trim() || leadTool?.toolName?.trim() || 'Live tool activity'
        const groupCounts = `${entry.group.toolCount} tools${
          entry.group.supportingItemCount
            ? ` - ${entry.group.supportingItemCount} supporting items`
            : ''
        }`

        return (
          <section
            key={entry.group.id}
            className={`${styles.row} ${styles.rowCard}`}
            data-testid={`conversation-tool-group-${entry.group.id}`}
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
                      item.kind === 'reasoning' ? reasoningMetaById.get(item.id) : undefined
                    return (
                      <ItemRow
                        key={item.id}
                        item={item}
                        pendingRequest={requestMap[item.id]}
                        onResolveUserInput={onResolveUserInput}
                        isExpanded={expandedItemIds.has(item.id)}
                        onToggleExpanded={toggleExpanded}
                        onRequestAutoScroll={requestAutoScroll}
                        reasoningMeta={reasoningMeta}
                      />
                    )
                  })}
                </div>
              ) : null}
            </div>
          </section>
        )
      })}
      {snapshot ? (
        <WorkingIndicator
          processingState={snapshot.processingState as ProcessingState}
          activeTurnId={snapshot.activeTurnId}
          reasoningLabel={latestReasoningLabel}
          processingStartedAt={processingStartedAt}
          lastCompletedAt={lastCompletedAt}
          lastDurationMs={lastDurationMs}
        />
      ) : null}
      {isLoading && groupedEntries.length === 0 ? (
        <div className={styles.empty}>Loading conversation...</div>
      ) : null}
      <div ref={bottomRef} />
    </div>
  )
}
