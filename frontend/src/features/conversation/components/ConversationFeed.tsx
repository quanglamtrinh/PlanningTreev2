import { useEffect, useMemo, useRef } from 'react'
import type {
  PendingUserInputRequest,
  ProcessingState,
  ThreadSnapshotV2,
  UserInputAnswer,
} from '../../../api/types'
import { ItemRow } from './ItemRow'
import styles from './ConversationFeed.module.css'
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
}: {
  snapshot: ThreadSnapshotV2 | null
  isLoading: boolean
  prefix?: React.ReactNode
  onResolveUserInput: (requestId: string, answers: UserInputAnswer[]) => Promise<void> | void
}) {
  const feedRef = useRef<HTMLDivElement>(null)
  const items = snapshot?.items ?? []
  const requestMap = useMemo(
    () => pendingRequestByItemId(snapshot?.pendingRequests ?? []),
    [snapshot?.pendingRequests],
  )

  useEffect(() => {
    if (!feedRef.current) {
      return
    }
    if (typeof feedRef.current.scrollTo === 'function') {
      feedRef.current.scrollTo({ top: feedRef.current.scrollHeight })
      return
    }
    feedRef.current.scrollTop = feedRef.current.scrollHeight
  }, [items, snapshot?.activeTurnId, snapshot?.processingState])

  return (
    <div ref={feedRef} className={styles.feed} data-testid="conversation-feed">
      {prefix}
      {items.length === 0 && !isLoading ? (
        <div className={styles.empty}>No conversation items yet.</div>
      ) : null}
      {items.map((item) => (
        <ItemRow
          key={item.id}
          item={item}
          pendingRequest={requestMap[item.id]}
          onResolveUserInput={onResolveUserInput}
        />
      ))}
      {snapshot ? (
        <WorkingIndicator
          processingState={snapshot.processingState as ProcessingState}
          activeTurnId={snapshot.activeTurnId}
        />
      ) : null}
      {isLoading && items.length === 0 ? (
        <div className={styles.empty}>Loading conversation…</div>
      ) : null}
    </div>
  )
}
