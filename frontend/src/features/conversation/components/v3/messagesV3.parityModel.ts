import type {
  ConversationItemV3,
  PendingUserInputRequestV3,
  ThreadSnapshotV3,
  UserInputItemV3,
} from '../../../../api/types'
import { buildToolGroupsV3, deriveVisibleMessageStateV3 } from './messagesV3.utils'

type PendingRequestStatus = PendingUserInputRequestV3['status']

export type PlanReadySuppressionReasonV3 =
  | 'none'
  | 'lane_not_execution'
  | 'not_ready'
  | 'failed'
  | 'missing_dismiss_key'
  | 'missing_revision_item'
  | 'blocked_pending_request'
  | 'superseded_by_user_message'
  | 'dismissed'

export type MessagesV3ParityModel = {
  visibleItemIds: string[]
  visibleItemKinds: ConversationItemV3['kind'][]
  pendingRequestIds: string[]
  inlineUserInputItemIds: string[]
  showPlanReadyCard: boolean
  planReadySuppressionReason: PlanReadySuppressionReasonV3
  toolGroupCount: number
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

function requestByRequestId(
  pendingRequests: PendingUserInputRequestV3[],
): Map<string, PendingUserInputRequestV3> {
  const next = new Map<string, PendingUserInputRequestV3>()
  for (const request of pendingRequests) {
    next.set(request.requestId, request)
  }
  return next
}

function effectiveUserInputStatus(
  item: UserInputItemV3,
  requestMapByRequestId: Map<string, PendingUserInputRequestV3>,
): PendingRequestStatus {
  const request = requestMapByRequestId.get(item.requestId)
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

function toSuppressionReason(options: {
  lane: ThreadSnapshotV3['lane'] | null
  ready: boolean
  failed: boolean
  hasDismissKey: boolean
  hasPlanRevisionItem: boolean
  hasBlockingPendingRequest: boolean
  supersededByUserMessage: boolean
  dismissed: boolean
}): PlanReadySuppressionReasonV3 {
  if (options.lane !== 'execution') {
    return 'lane_not_execution'
  }
  if (!options.ready) {
    return 'not_ready'
  }
  if (options.failed) {
    return 'failed'
  }
  if (!options.hasDismissKey) {
    return 'missing_dismiss_key'
  }
  if (!options.hasPlanRevisionItem) {
    return 'missing_revision_item'
  }
  if (options.hasBlockingPendingRequest) {
    return 'blocked_pending_request'
  }
  if (options.supersededByUserMessage) {
    return 'superseded_by_user_message'
  }
  if (options.dismissed) {
    return 'dismissed'
  }
  return 'none'
}

export function deriveMessagesV3ParityModel(
  snapshot: ThreadSnapshotV3 | null,
  options: {
    dismissedPlanReadyKeys?: string[]
  } = {},
): MessagesV3ParityModel {
  const pendingRequests = snapshot?.uiSignals.activeUserInputRequests ?? []
  const requestMapByRequestId = requestByRequestId(pendingRequests)
  const visibleState = deriveVisibleMessageStateV3(snapshot)
  const visibleItems = visibleState.visibleItems.filter((item) => {
    if (item.kind !== 'userInput') {
      return true
    }
    return !isPendingRequestStatus(effectiveUserInputStatus(item, requestMapByRequestId))
  })
  const groupedEntries = buildToolGroupsV3(visibleItems)
  const toolGroupCount = groupedEntries.filter((entry) => entry.kind === 'toolGroup').length

  const pendingRequestIds = [...pendingRequests]
    .filter((request) => isPendingRequestStatus(request.status))
    .sort(
      (left, right) =>
        left.createdAt.localeCompare(right.createdAt) ||
        left.requestId.localeCompare(right.requestId),
    )
    .map((request) => request.requestId)

  const inlineUserInputItemIds = visibleItems
    .filter((item): item is UserInputItemV3 => item.kind === 'userInput')
    .map((item) => item.id)

  const itemById = new Map(snapshot?.items.map((item) => [item.id, item]) ?? [])
  const planReadySignal = snapshot?.uiSignals.planReady
  const planReadyDismissKey = buildPlanReadyDismissKey(
    snapshot?.threadId,
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
  const dismissedPlanReadyKeys = new Set(options.dismissedPlanReadyKeys ?? [])
  const suppressionReason = toSuppressionReason({
    lane: snapshot?.lane ?? null,
    ready: Boolean(planReadySignal?.ready),
    failed: Boolean(planReadySignal?.failed),
    hasDismissKey: Boolean(planReadyDismissKey),
    hasPlanRevisionItem: Boolean(hasPlanRevisionItem),
    hasBlockingPendingRequest,
    supersededByUserMessage,
    dismissed: dismissedPlanReadyKeys.has(String(planReadyDismissKey ?? '')),
  })
  const showPlanReadyCard = suppressionReason === 'none'

  return {
    visibleItemIds: visibleItems.map((item) => item.id),
    visibleItemKinds: visibleItems.map((item) => item.kind),
    pendingRequestIds,
    inlineUserInputItemIds,
    showPlanReadyCard,
    planReadySuppressionReason: suppressionReason,
    toolGroupCount,
  }
}
