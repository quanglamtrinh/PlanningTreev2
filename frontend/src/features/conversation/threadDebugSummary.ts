import type {
  ConversationItem,
  PendingUserInputRequest,
  ThreadEventV2,
  ThreadRole,
  ThreadSnapshotV2,
} from '../../api/types'

const ITEM_PREVIEW_LIMIT = 4
const TEXT_PREVIEW_LIMIT = 120

function previewText(value: string | null | undefined): string | null {
  const text = String(value ?? '').trim()
  if (!text) {
    return null
  }
  return text.length > TEXT_PREVIEW_LIMIT
    ? `${text.slice(0, TEXT_PREVIEW_LIMIT - 3)}...`
    : text
}

export function summarizeConversationItem(item: ConversationItem): Record<string, unknown> {
  if (item.kind === 'message') {
    return {
      id: item.id,
      kind: item.kind,
      status: item.status,
      role: item.role,
      text: previewText(item.text),
    }
  }
  if (item.kind === 'reasoning') {
    return {
      id: item.id,
      kind: item.kind,
      status: item.status,
      summaryText: previewText(item.summaryText),
      detailText: previewText(item.detailText),
    }
  }
  if (item.kind === 'plan') {
    return {
      id: item.id,
      kind: item.kind,
      status: item.status,
      title: previewText(item.title),
      text: previewText(item.text),
      stepCount: item.steps.length,
    }
  }
  if (item.kind === 'tool') {
    return {
      id: item.id,
      kind: item.kind,
      status: item.status,
      toolType: item.toolType,
      title: previewText(item.title),
      toolName: previewText(item.toolName),
      outputText: previewText(item.outputText),
      outputFileCount: item.outputFiles.length,
      exitCode: item.exitCode,
    }
  }
  if (item.kind === 'userInput') {
    return {
      id: item.id,
      kind: item.kind,
      status: item.status,
      requestId: item.requestId,
      title: previewText(item.title),
      questionCount: item.questions.length,
      answerCount: item.answers.length,
    }
  }
  if (item.kind === 'status') {
    return {
      id: item.id,
      kind: item.kind,
      status: item.status,
      code: item.code,
      label: previewText(item.label),
      detail: previewText(item.detail),
    }
  }
  return {
    id: item.id,
    kind: item.kind,
    status: item.status,
    code: item.code,
    title: previewText(item.title),
    message: previewText(item.message),
    recoverable: item.recoverable,
  }
}

function summarizePendingRequest(request: PendingUserInputRequest): Record<string, unknown> {
  return {
    requestId: request.requestId,
    itemId: request.itemId,
    status: request.status,
    answerCount: request.answers.length,
  }
}

function summarizeItems(items: ConversationItem[]): Record<string, unknown> {
  return {
    count: items.length,
    firstItems: items.slice(0, ITEM_PREVIEW_LIMIT).map(summarizeConversationItem),
    lastItems: items.slice(-ITEM_PREVIEW_LIMIT).map(summarizeConversationItem),
  }
}

export function summarizeThreadSnapshot(
  snapshot: ThreadSnapshotV2 | null | undefined,
): Record<string, unknown> | null {
  if (!snapshot) {
    return null
  }

  return {
    projectId: snapshot.projectId,
    nodeId: snapshot.nodeId,
    threadRole: snapshot.threadRole,
    threadId: snapshot.threadId,
    activeTurnId: snapshot.activeTurnId,
    processingState: snapshot.processingState,
    snapshotVersion: snapshot.snapshotVersion,
    createdAt: snapshot.createdAt,
    updatedAt: snapshot.updatedAt,
    pendingRequestCount: snapshot.pendingRequests.length,
    pendingRequests: snapshot.pendingRequests
      .slice(0, ITEM_PREVIEW_LIMIT)
      .map(summarizePendingRequest),
    items: summarizeItems(snapshot.items),
  }
}

export function summarizeThreadEvent(event: ThreadEventV2): Record<string, unknown> {
  const base = {
    eventId: event.eventId,
    type: event.type,
    threadRole: event.threadRole,
    snapshotVersion: event.snapshotVersion,
    occurredAt: event.occurredAt,
  }

  if (event.type === 'thread.snapshot') {
    return {
      ...base,
      snapshot: summarizeThreadSnapshot(event.payload.snapshot),
    }
  }

  if (event.type === 'conversation.item.upsert') {
    return {
      ...base,
      item: summarizeConversationItem(event.payload.item),
    }
  }

  if (event.type === 'conversation.item.patch') {
    return {
      ...base,
      itemId: event.payload.itemId,
      patchKind: event.payload.patch.kind,
      patchStatus: event.payload.patch.status ?? null,
    }
  }

  if (event.type === 'thread.lifecycle') {
    return {
      ...base,
      activeTurnId: event.payload.activeTurnId,
      processingState: event.payload.processingState,
      state: event.payload.state,
      detail: previewText(event.payload.detail),
    }
  }

  if (event.type === 'conversation.request.user_input.requested') {
    return {
      ...base,
      requestId: event.payload.requestId,
      itemId: event.payload.itemId,
      item: summarizeConversationItem(event.payload.item),
      pendingRequest: summarizePendingRequest(event.payload.pendingRequest),
    }
  }

  if (event.type === 'conversation.request.user_input.resolved') {
    return {
      ...base,
      requestId: event.payload.requestId,
      itemId: event.payload.itemId,
      status: event.payload.status,
      answerCount: event.payload.answers.length,
    }
  }

  if (event.type === 'thread.reset') {
    return {
      ...base,
      threadId: event.payload.threadId,
    }
  }

  return {
    ...base,
    errorItem: summarizeConversationItem(event.payload.errorItem),
  }
}

export function summarizeThreadStoreState(state: {
  activeProjectId: string | null
  activeNodeId: string | null
  activeThreadId: string | null
  activeThreadRole: ThreadRole | null
  isLoading: boolean
  isSending: boolean
  streamStatus: string
  lastEventId: string | null
  lastSnapshotVersion: number | null
  error: string | null
  snapshot: ThreadSnapshotV2 | null
}): Record<string, unknown> {
  return {
    activeProjectId: state.activeProjectId,
    activeNodeId: state.activeNodeId,
    activeThreadId: state.activeThreadId,
    activeThreadRole: state.activeThreadRole,
    isLoading: state.isLoading,
    isSending: state.isSending,
    streamStatus: state.streamStatus,
    lastEventId: state.lastEventId,
    lastSnapshotVersion: state.lastSnapshotVersion,
    error: state.error,
    snapshot: summarizeThreadSnapshot(state.snapshot),
  }
}
