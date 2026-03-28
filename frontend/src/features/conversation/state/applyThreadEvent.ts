import type {
  ConversationItem,
  ErrorItem,
  ErrorPatch,
  ItemPatch,
  PendingUserInputRequest,
  PlanItem,
  PlanPatch,
  ReasoningItem,
  ReasoningPatch,
  StatusItem,
  StatusPatch,
  ThreadEventV2,
  ThreadSnapshotV2,
  ToolItem,
  ToolPatch,
  UserInputItem,
  UserInputPatch,
  ConversationMessageItem,
  MessagePatch,
} from '../../../api/types'

export class ThreadEventApplyError extends Error {
  code: 'missing_snapshot' | 'missing_item' | 'kind_mismatch'

  constructor(code: ThreadEventApplyError['code'], message: string) {
    super(message)
    this.name = 'ThreadEventApplyError'
    this.code = code
  }
}

function sortItems(items: ConversationItem[]): ConversationItem[] {
  return [...items].sort((left, right) => {
    if (left.sequence !== right.sequence) {
      return left.sequence - right.sequence
    }
    return left.createdAt.localeCompare(right.createdAt)
  })
}

function upsertItem(items: ConversationItem[], item: ConversationItem): ConversationItem[] {
  const next = [...items]
  const existingIndex = next.findIndex((candidate) => candidate.id === item.id)
  if (existingIndex >= 0) {
    next[existingIndex] = item
  } else {
    next.push(item)
  }
  return sortItems(next)
}

function replacePendingRequest(
  requests: PendingUserInputRequest[],
  pendingRequest: PendingUserInputRequest,
): PendingUserInputRequest[] {
  const next = [...requests]
  const existingIndex = next.findIndex((candidate) => candidate.requestId === pendingRequest.requestId)
  if (existingIndex >= 0) {
    next[existingIndex] = pendingRequest
  } else {
    next.push(pendingRequest)
  }
  return next
}

function patchMessageItem(item: ConversationMessageItem, patch: MessagePatch): ConversationMessageItem {
  return {
    ...item,
    text: patch.textAppend ? `${item.text}${patch.textAppend}` : item.text,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchReasoningItem(item: ReasoningItem, patch: ReasoningPatch): ReasoningItem {
  const nextDetailText =
    patch.detailTextAppend === undefined
      ? item.detailText
      : `${item.detailText ?? ''}${patch.detailTextAppend}`
  return {
    ...item,
    summaryText: patch.summaryTextAppend ? `${item.summaryText}${patch.summaryTextAppend}` : item.summaryText,
    detailText: nextDetailText,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchPlanItem(item: PlanItem, patch: PlanPatch): PlanItem {
  return {
    ...item,
    text: patch.textAppend ? `${item.text}${patch.textAppend}` : item.text,
    steps: patch.stepsReplace ?? item.steps,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchToolItem(item: ToolItem, patch: ToolPatch): ToolItem {
  const outputFiles = patch.outputFilesReplace
    ? [...patch.outputFilesReplace]
    : patch.outputFilesAppend
      ? [...item.outputFiles, ...patch.outputFilesAppend]
      : item.outputFiles
  return {
    ...item,
    title: patch.title ?? item.title,
    argumentsText: patch.argumentsText !== undefined ? patch.argumentsText : item.argumentsText,
    outputText: patch.outputTextAppend ? `${item.outputText}${patch.outputTextAppend}` : item.outputText,
    outputFiles,
    exitCode: patch.exitCode !== undefined ? patch.exitCode : item.exitCode,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchUserInputItem(item: UserInputItem, patch: UserInputPatch): UserInputItem {
  return {
    ...item,
    answers: patch.answersReplace ?? item.answers,
    resolvedAt: patch.resolvedAt !== undefined ? patch.resolvedAt : item.resolvedAt,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchStatusItem(item: StatusItem, patch: StatusPatch): StatusItem {
  return {
    ...item,
    label: patch.label ?? item.label,
    detail: patch.detail !== undefined ? patch.detail : item.detail,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchErrorItem(item: ErrorItem, patch: ErrorPatch): ErrorItem {
  return {
    ...item,
    message: patch.message ?? item.message,
    relatedItemId: patch.relatedItemId !== undefined ? patch.relatedItemId : item.relatedItemId,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function applyItemPatch(item: ConversationItem, patch: ItemPatch): ConversationItem {
  if (item.kind !== patch.kind) {
    throw new ThreadEventApplyError(
      'kind_mismatch',
      `Expected ${item.kind} patch but received ${patch.kind}.`,
    )
  }

  switch (patch.kind) {
    case 'message':
      return patchMessageItem(item as ConversationMessageItem, patch)
    case 'reasoning':
      return patchReasoningItem(item as ReasoningItem, patch)
    case 'plan':
      return patchPlanItem(item as PlanItem, patch)
    case 'tool':
      return patchToolItem(item as ToolItem, patch)
    case 'userInput':
      return patchUserInputItem(item as UserInputItem, patch)
    case 'status':
      return patchStatusItem(item as StatusItem, patch)
    case 'error':
      return patchErrorItem(item as ErrorItem, patch)
    default:
      return item
  }
}

export function applyThreadEvent(
  snapshot: ThreadSnapshotV2 | null,
  event: ThreadEventV2,
): ThreadSnapshotV2 {
  if (event.type === 'thread.snapshot') {
    return event.payload.snapshot
  }

  if (!snapshot) {
    throw new ThreadEventApplyError(
      'missing_snapshot',
      'Received a thread event before a snapshot was available.',
    )
  }

  const nextSnapshotVersion = event.snapshotVersion ?? snapshot.snapshotVersion
  const nextUpdatedAt = event.occurredAt ?? snapshot.updatedAt

  switch (event.type) {
    case 'conversation.item.upsert':
      return {
        ...snapshot,
        items: upsertItem(snapshot.items, event.payload.item),
        snapshotVersion: nextSnapshotVersion,
        updatedAt: event.payload.item.updatedAt || nextUpdatedAt,
      }

    case 'conversation.item.patch': {
      const index = snapshot.items.findIndex((item) => item.id === event.payload.itemId)
      if (index < 0) {
        throw new ThreadEventApplyError(
          'missing_item',
          `Cannot patch missing conversation item ${event.payload.itemId}.`,
        )
      }
      const nextItems = [...snapshot.items]
      nextItems[index] = applyItemPatch(nextItems[index], event.payload.patch)
      return {
        ...snapshot,
        items: sortItems(nextItems),
        snapshotVersion: nextSnapshotVersion,
        updatedAt: event.payload.patch.updatedAt,
      }
    }

    case 'thread.lifecycle':
      return {
        ...snapshot,
        activeTurnId: event.payload.activeTurnId,
        processingState: event.payload.processingState,
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }

    case 'conversation.request.user_input.requested':
      return {
        ...snapshot,
        pendingRequests: replacePendingRequest(snapshot.pendingRequests, event.payload.pendingRequest),
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }

    case 'conversation.request.user_input.resolved':
      return {
        ...snapshot,
        pendingRequests: snapshot.pendingRequests.map((request) =>
          request.requestId === event.payload.requestId
            ? {
                ...request,
                status: event.payload.status,
                answers: event.payload.answers,
                resolvedAt: event.payload.resolvedAt,
              }
            : request,
        ),
        snapshotVersion: nextSnapshotVersion,
        updatedAt: event.payload.resolvedAt ?? nextUpdatedAt,
      }

    case 'thread.reset':
      return {
        ...snapshot,
        threadId: event.payload.threadId ?? snapshot.threadId,
        activeTurnId: null,
        processingState: 'idle',
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }

    case 'thread.error':
      return {
        ...snapshot,
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }

    default:
      return snapshot
  }
}
