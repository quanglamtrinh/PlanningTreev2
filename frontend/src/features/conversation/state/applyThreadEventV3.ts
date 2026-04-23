import type {
  ConversationItemV3,
  DiffChangeV3,
  DiffItemV3,
  DiffPatchV3,
  ErrorItemV3,
  ErrorPatchV3,
  ExploreItemV3,
  ExplorePatchV3,
  ItemPatchV3,
  MessagePatchV3,
  PendingUserInputRequestV3,
  ReasoningItemV3,
  ReasoningPatchV3,
  ReviewItemV3,
  ReviewPatchV3,
  StatusItemV3,
  StatusPatchV3,
  ThreadEventV3,
  ThreadSnapshotV3,
  ToolItemV3,
  ToolPatchV3,
  UserInputAnswerV3,
  UserInputItemV3,
  UserInputPatchV3,
  ConversationMessageItemV3,
} from '../../../api/types'

export class ThreadEventApplyErrorV3 extends Error {
  code:
    | 'missing_snapshot'
    | 'missing_item'
    | 'kind_mismatch'
    | 'unsupported_patch_kind'
    | 'invalid_state'

  constructor(code: ThreadEventApplyErrorV3['code'], message: string) {
    super(message)
    this.name = 'ThreadEventApplyErrorV3'
    this.code = code
  }
}

export type ThreadEventApplyDiagnosticsV3 = {
  fastAppendUsed: boolean
  fastAppendFallback: boolean
}

export type ThreadApplyOperationKindV3 = 'insert' | 'reorder' | 'patch-content' | 'patch-meta'

type ThreadSnapshotNormalizedV1 = {
  projectId: string
  nodeId: string
  threadId: string | null
  threadRole: ThreadSnapshotV3['threadRole']
  activeTurnId: string | null
  processingState: ThreadSnapshotV3['processingState']
  snapshotVersion: number
  createdAt: string
  updatedAt: string
  itemsById: Record<string, ConversationItemV3>
  orderedItemIds: string[]
  uiSignals: ThreadSnapshotV3['uiSignals']
  historyMeta: ThreadSnapshotV3['historyMeta'] | undefined
}

function markFastAppendUsed(diagnostics?: ThreadEventApplyDiagnosticsV3): void {
  if (diagnostics) {
    diagnostics.fastAppendUsed = true
  }
}

function markFastAppendFallback(diagnostics?: ThreadEventApplyDiagnosticsV3): void {
  if (diagnostics) {
    diagnostics.fastAppendFallback = true
  }
}

function compareConversationItemOrder(left: ConversationItemV3, right: ConversationItemV3): number {
  if (left.sequence !== right.sequence) {
    return left.sequence - right.sequence
  }
  const createdAtCompare = left.createdAt.localeCompare(right.createdAt)
  if (createdAtCompare !== 0) {
    return createdAtCompare
  }
  return left.id.localeCompare(right.id)
}

function sortOrderedItemIds(
  itemsById: Record<string, ConversationItemV3>,
  orderedItemIds: string[],
): string[] {
  const next = [...orderedItemIds]
  next.sort((leftId, rightId) => {
    const left = itemsById[leftId]
    const right = itemsById[rightId]
    if (!left || !right) {
      throw new ThreadEventApplyErrorV3(
        'invalid_state',
        `Missing item reference while sorting ids: left=${leftId}, right=${rightId}.`,
      )
    }
    return compareConversationItemOrder(left, right)
  })
  return next
}

function areAnswersEqual(left: UserInputAnswerV3[], right: UserInputAnswerV3[]): boolean {
  if (left === right) {
    return true
  }
  if (left.length !== right.length) {
    return false
  }
  for (let index = 0; index < left.length; index += 1) {
    const leftAnswer = left[index]
    const rightAnswer = right[index]
    if (
      leftAnswer.questionId !== rightAnswer.questionId ||
      leftAnswer.value !== rightAnswer.value ||
      leftAnswer.label !== rightAnswer.label
    ) {
      return false
    }
  }
  return true
}

function arePendingUserInputRequestsEqual(
  left: PendingUserInputRequestV3[],
  right: PendingUserInputRequestV3[],
): boolean {
  if (left === right) {
    return true
  }
  if (left.length !== right.length) {
    return false
  }
  for (let index = 0; index < left.length; index += 1) {
    const leftRequest = left[index]
    const rightRequest = right[index]
    if (
      leftRequest.requestId !== rightRequest.requestId ||
      leftRequest.itemId !== rightRequest.itemId ||
      leftRequest.threadId !== rightRequest.threadId ||
      leftRequest.turnId !== rightRequest.turnId ||
      leftRequest.status !== rightRequest.status ||
      leftRequest.createdAt !== rightRequest.createdAt ||
      leftRequest.submittedAt !== rightRequest.submittedAt ||
      leftRequest.resolvedAt !== rightRequest.resolvedAt ||
      !areAnswersEqual(leftRequest.answers, rightRequest.answers)
    ) {
      return false
    }
  }
  return true
}

function arePlanReadySignalsEqual(
  left: ThreadSnapshotV3['uiSignals']['planReady'],
  right: ThreadSnapshotV3['uiSignals']['planReady'],
): boolean {
  return (
    left.planItemId === right.planItemId &&
    left.revision === right.revision &&
    left.ready === right.ready &&
    left.failed === right.failed
  )
}

function normalizeSnapshot(snapshot: ThreadSnapshotV3): ThreadSnapshotNormalizedV1 {
  const itemsById: Record<string, ConversationItemV3> = {}
  const orderedItemIds: string[] = []
  for (const item of snapshot.items) {
    if (itemsById[item.id] !== undefined) {
      throw new ThreadEventApplyErrorV3(
        'invalid_state',
        `Duplicate item id in snapshot.items: ${item.id}.`,
      )
    }
    itemsById[item.id] = item
    orderedItemIds.push(item.id)
  }
  return {
    projectId: snapshot.projectId,
    nodeId: snapshot.nodeId,
    threadId: snapshot.threadId,
    threadRole: snapshot.threadRole,
    activeTurnId: snapshot.activeTurnId,
    processingState: snapshot.processingState,
    snapshotVersion: snapshot.snapshotVersion,
    createdAt: snapshot.createdAt,
    updatedAt: snapshot.updatedAt,
    itemsById,
    orderedItemIds,
    uiSignals: snapshot.uiSignals,
    historyMeta: snapshot.historyMeta,
  }
}

function materializeItems(
  previousSnapshot: ThreadSnapshotV3,
  normalized: ThreadSnapshotNormalizedV1,
): ConversationItemV3[] {
  const previousItems = previousSnapshot.items
  const nextOrderedItemIds = normalized.orderedItemIds
  const nextItemsById = normalized.itemsById

  if (previousItems.length === nextOrderedItemIds.length) {
    let sameOrder = true
    for (let index = 0; index < nextOrderedItemIds.length; index += 1) {
      if (previousItems[index].id !== nextOrderedItemIds[index]) {
        sameOrder = false
        break
      }
    }
    if (sameOrder) {
      let changed = false
      const nextItems = [...previousItems]
      for (let index = 0; index < nextOrderedItemIds.length; index += 1) {
        const itemId = nextOrderedItemIds[index]
        const nextItem = nextItemsById[itemId]
        if (!nextItem) {
          throw new ThreadEventApplyErrorV3(
            'invalid_state',
            `orderedItemIds references missing item id: ${itemId}.`,
          )
        }
        if (previousItems[index] !== nextItem) {
          nextItems[index] = nextItem
          changed = true
        }
      }
      return changed ? nextItems : previousItems
    }
  }

  return nextOrderedItemIds.map((itemId) => {
    const item = nextItemsById[itemId]
    if (!item) {
      throw new ThreadEventApplyErrorV3(
        'invalid_state',
        `orderedItemIds references missing item id: ${itemId}.`,
      )
    }
    return item
  })
}

function materializeSnapshot(
  previousSnapshot: ThreadSnapshotV3,
  normalized: ThreadSnapshotNormalizedV1,
): ThreadSnapshotV3 {
  return {
    projectId: normalized.projectId,
    nodeId: normalized.nodeId,
    threadId: normalized.threadId,
    threadRole: normalized.threadRole,
    activeTurnId: normalized.activeTurnId,
    processingState: normalized.processingState,
    snapshotVersion: normalized.snapshotVersion,
    createdAt: normalized.createdAt,
    updatedAt: normalized.updatedAt,
    items: materializeItems(previousSnapshot, normalized),
    uiSignals: normalized.uiSignals,
    historyMeta: normalized.historyMeta,
  }
}

function patchMessageItem(item: ConversationMessageItemV3, patch: MessagePatchV3): ConversationMessageItemV3 {
  return {
    ...item,
    text: patch.textAppend ? `${item.text}${patch.textAppend}` : item.text,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchReasoningItem(item: ReasoningItemV3, patch: ReasoningPatchV3): ReasoningItemV3 {
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

function patchToolItem(item: ToolItemV3, patch: ToolPatchV3): ToolItemV3 {
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

function patchExploreItem(item: ExploreItemV3, patch: ExplorePatchV3): ExploreItemV3 {
  return {
    ...item,
    title: patch.title !== undefined ? patch.title : item.title,
    text: patch.textAppend ? `${item.text}${patch.textAppend}` : item.text,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchUserInputItem(item: UserInputItemV3, patch: UserInputPatchV3): UserInputItemV3 {
  return {
    ...item,
    answers: patch.answersReplace ?? item.answers,
    resolvedAt: patch.resolvedAt !== undefined ? patch.resolvedAt : item.resolvedAt,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchReviewItem(item: ReviewItemV3, patch: ReviewPatchV3): ReviewItemV3 {
  return {
    ...item,
    title: patch.title !== undefined ? patch.title : item.title,
    text: patch.textAppend ? `${item.text}${patch.textAppend}` : item.text,
    disposition: patch.disposition !== undefined ? patch.disposition : item.disposition,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function normalizeDiffChangeKind(value: string | null | undefined): DiffChangeV3['kind'] {
  const normalized = (value ?? '').trim().toLowerCase()
  if (normalized === 'add' || normalized === 'create' || normalized === 'created' || normalized === 'new') {
    return 'add'
  }
  if (
    normalized === 'delete' ||
    normalized === 'deleted' ||
    normalized === 'remove' ||
    normalized === 'removed'
  ) {
    return 'delete'
  }
  return 'modify'
}

function diffChangeKindToChangeType(kind: DiffChangeV3['kind']): 'created' | 'updated' | 'deleted' {
  if (kind === 'add') {
    return 'created'
  }
  if (kind === 'delete') {
    return 'deleted'
  }
  return 'updated'
}

function diffChangeTypeToKind(value: string | null | undefined): DiffChangeV3['kind'] {
  const normalized = (value ?? '').trim().toLowerCase()
  if (normalized === 'created' || normalized === 'create' || normalized === 'add') {
    return 'add'
  }
  if (normalized === 'deleted' || normalized === 'delete' || normalized === 'remove' || normalized === 'removed') {
    return 'delete'
  }
  return 'modify'
}

function normalizePatchText(value: string | null | undefined): string | null {
  if (typeof value !== 'string') {
    return null
  }
  return value.trim() ? value : null
}

function diffChangesFromFiles(files: DiffItemV3['files']): DiffChangeV3[] {
  return files
    .map((file) => {
      const path = file.path?.trim()
      if (!path) {
        return null
      }
      return {
        path,
        kind: diffChangeTypeToKind(file.changeType),
        diff: normalizePatchText(file.patchText),
        summary: file.summary ?? null,
      }
    })
    .filter((change): change is DiffChangeV3 => change !== null)
}

function diffFilesFromChanges(changes: DiffChangeV3[]): DiffItemV3['files'] {
  return changes
    .map((change) => {
      const path = change.path?.trim()
      if (!path) {
        return null
      }
      const kind = normalizeDiffChangeKind(change.kind)
      return {
        path,
        changeType: diffChangeKindToChangeType(kind),
        summary: change.summary ?? null,
        patchText: normalizePatchText(change.diff),
      }
    })
    .filter((file): file is DiffItemV3['files'][number] => file !== null)
}

function patchDiffItem(item: DiffItemV3, patch: DiffPatchV3): DiffItemV3 {
  const currentChanges = Array.isArray(item.changes)
    ? [...item.changes]
    : diffChangesFromFiles(item.files)

  let nextChanges = currentChanges
  if (patch.changesReplace !== undefined) {
    nextChanges = [...patch.changesReplace]
  } else if (patch.changesAppend && patch.changesAppend.length > 0) {
    nextChanges = [...currentChanges, ...patch.changesAppend]
  } else if (patch.filesReplace !== undefined) {
    nextChanges = diffChangesFromFiles(patch.filesReplace)
  } else if (patch.filesAppend && patch.filesAppend.length > 0) {
    nextChanges = [...currentChanges, ...diffChangesFromFiles(patch.filesAppend)]
  }

  return {
    ...item,
    title: patch.title !== undefined ? patch.title : item.title,
    summaryText: patch.summaryText !== undefined ? patch.summaryText : item.summaryText,
    changes: nextChanges,
    files: diffFilesFromChanges(nextChanges),
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchStatusItem(item: StatusItemV3, patch: StatusPatchV3): StatusItemV3 {
  return {
    ...item,
    label: patch.label ?? item.label,
    detail: patch.detail !== undefined ? patch.detail : item.detail,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function patchErrorItem(item: ErrorItemV3, patch: ErrorPatchV3): ErrorItemV3 {
  return {
    ...item,
    message: patch.message ?? item.message,
    relatedItemId: patch.relatedItemId !== undefined ? patch.relatedItemId : item.relatedItemId,
    status: patch.status ?? item.status,
    updatedAt: patch.updatedAt,
  }
}

function applyItemPatch(item: ConversationItemV3, patch: ItemPatchV3): ConversationItemV3 {
  if (item.kind !== patch.kind) {
    throw new ThreadEventApplyErrorV3(
      'kind_mismatch',
      `Expected ${item.kind} patch but received ${patch.kind}.`,
    )
  }

  switch (patch.kind) {
    case 'message':
      return patchMessageItem(item as ConversationMessageItemV3, patch)
    case 'reasoning':
      return patchReasoningItem(item as ReasoningItemV3, patch)
    case 'tool':
      return patchToolItem(item as ToolItemV3, patch)
    case 'explore':
      return patchExploreItem(item as ExploreItemV3, patch)
    case 'userInput':
      return patchUserInputItem(item as UserInputItemV3, patch)
    case 'review':
      return patchReviewItem(item as ReviewItemV3, patch)
    case 'diff':
      return patchDiffItem(item as DiffItemV3, patch)
    case 'status':
      return patchStatusItem(item as StatusItemV3, patch)
    case 'error':
      return patchErrorItem(item as ErrorItemV3, patch)
    default: {
      const unknownPatch = patch as { kind?: unknown }
      throw new ThreadEventApplyErrorV3(
        'unsupported_patch_kind',
        `Unsupported patch kind: ${String(unknownPatch.kind ?? 'unknown')}.`,
      )
    }
  }
}

function isPatchContentOperation(patch: ItemPatchV3): boolean {
  switch (patch.kind) {
    case 'message':
      return typeof patch.textAppend === 'string' && patch.textAppend.length > 0
    case 'reasoning':
      return (
        (typeof patch.summaryTextAppend === 'string' && patch.summaryTextAppend.length > 0) ||
        (typeof patch.detailTextAppend === 'string' && patch.detailTextAppend.length > 0)
      )
    case 'tool':
      return (
        patch.title !== undefined ||
        patch.argumentsText !== undefined ||
        (typeof patch.outputTextAppend === 'string' && patch.outputTextAppend.length > 0) ||
        patch.outputFilesAppend !== undefined ||
        patch.outputFilesReplace !== undefined
      )
    case 'explore':
      return patch.title !== undefined || (typeof patch.textAppend === 'string' && patch.textAppend.length > 0)
    case 'userInput':
      return patch.answersReplace !== undefined
    case 'review':
      return (
        patch.title !== undefined ||
        (typeof patch.textAppend === 'string' && patch.textAppend.length > 0) ||
        patch.disposition !== undefined
      )
    case 'diff':
      return (
        patch.title !== undefined ||
        patch.summaryText !== undefined ||
        patch.changesAppend !== undefined ||
        patch.changesReplace !== undefined ||
        patch.filesAppend !== undefined ||
        patch.filesReplace !== undefined
      )
    case 'status':
      return patch.label !== undefined || patch.detail !== undefined
    case 'error':
      return patch.message !== undefined || patch.relatedItemId !== undefined
    default:
      return false
  }
}

function isUpsertReorder(
  existing: ConversationItemV3,
  incoming: ConversationItemV3,
): boolean {
  return (
    existing.sequence !== incoming.sequence ||
    existing.createdAt !== incoming.createdAt ||
    existing.id !== incoming.id
  )
}

export function classifyThreadEventOperationV3(
  snapshot: ThreadSnapshotV3 | null,
  event: ThreadEventV3,
): ThreadApplyOperationKindV3 | null {
  if (event.type === 'conversation.item.upsert.v3') {
    const existing = snapshot?.items.find((item) => item.id === event.payload.item.id) ?? null
    if (existing == null) {
      return 'insert'
    }
    return isUpsertReorder(existing, event.payload.item) ? 'reorder' : 'patch-meta'
  }

  if (event.type === 'conversation.item.patch.v3') {
    return isPatchContentOperation(event.payload.patch) ? 'patch-content' : 'patch-meta'
  }

  return null
}

function isAppendSafeMessagePatch(patch: MessagePatchV3): boolean {
  const patchRecord = patch as unknown as Record<string, unknown>
  const patchKeys = Object.keys(patchRecord)
  return patchKeys.every((key) =>
    key === 'kind' || key === 'textAppend' || key === 'status' || key === 'updatedAt',
  )
}

function tryApplyFastMessageAppendPatch(
  snapshot: ThreadSnapshotV3,
  itemId: string,
  patch: MessagePatchV3,
  {
    nextSnapshotVersion,
    nextUpdatedAt,
    diagnostics,
  }: {
    nextSnapshotVersion: number
    nextUpdatedAt: string
    diagnostics?: ThreadEventApplyDiagnosticsV3
  },
): ThreadSnapshotV3 | null {
  if (!isAppendSafeMessagePatch(patch)) {
    return null
  }
  const textAppend = typeof patch.textAppend === 'string' ? patch.textAppend : ''
  if (!textAppend) {
    return null
  }

  const targetIndex = snapshot.items.findIndex((item) => item.id === itemId)
  if (targetIndex < 0) {
    return null
  }
  const target = snapshot.items[targetIndex]
  if (target?.kind !== 'message') {
    return null
  }

  const nextItem: ConversationMessageItemV3 = {
    ...target,
    text: `${target.text}${textAppend}`,
    status: patch.status ?? target.status,
    updatedAt: patch.updatedAt,
  }
  const nextItems = [...snapshot.items]
  nextItems[targetIndex] = nextItem
  markFastAppendUsed(diagnostics)
  return {
    ...snapshot,
    snapshotVersion: nextSnapshotVersion,
    updatedAt: patch.updatedAt ?? nextUpdatedAt,
    items: nextItems,
  }
}

export function applyOptimisticUserInputSubmissionV3(
  snapshot: ThreadSnapshotV3,
  requestId: string,
  answers: UserInputAnswerV3[],
  submittedAt: string,
): ThreadSnapshotV3 {
  const normalized = normalizeSnapshot(snapshot)
  const normalizedAnswers = answers.map((answer) => ({ ...answer }))

  let nextItemsById = normalized.itemsById
  for (const itemId of normalized.orderedItemIds) {
    const item = normalized.itemsById[itemId]
    if (item.kind !== 'userInput' || item.requestId !== requestId) {
      continue
    }

    const hasChanged =
      item.status !== 'answer_submitted' ||
      item.updatedAt !== submittedAt ||
      !areAnswersEqual(item.answers, normalizedAnswers)

    if (!hasChanged) {
      continue
    }
    if (nextItemsById === normalized.itemsById) {
      nextItemsById = { ...normalized.itemsById }
    }
    nextItemsById[itemId] = {
      ...item,
      answers: [...normalizedAnswers],
      status: 'answer_submitted',
      updatedAt: submittedAt,
    }
  }

  const currentRequests = normalized.uiSignals.activeUserInputRequests
  let nextRequests = currentRequests
  for (let index = 0; index < currentRequests.length; index += 1) {
    const request = currentRequests[index]
    if (request.requestId !== requestId) {
      continue
    }
    const hasChanged =
      request.status !== 'answer_submitted' ||
      request.submittedAt !== submittedAt ||
      !areAnswersEqual(request.answers, normalizedAnswers)
    if (!hasChanged) {
      continue
    }
    if (nextRequests === currentRequests) {
      nextRequests = [...currentRequests]
    }
    nextRequests[index] = {
      ...request,
      status: 'answer_submitted',
      answers: [...normalizedAnswers],
      submittedAt,
    }
  }

  const nextUiSignals =
    nextRequests === currentRequests
      ? normalized.uiSignals
      : {
          ...normalized.uiSignals,
          activeUserInputRequests: nextRequests,
        }

  return materializeSnapshot(snapshot, {
    ...normalized,
    itemsById: nextItemsById,
    uiSignals: nextUiSignals,
    updatedAt: submittedAt,
  })
}

export function applyThreadEventV3(
  snapshot: ThreadSnapshotV3 | null,
  event: ThreadEventV3,
  diagnostics?: ThreadEventApplyDiagnosticsV3,
): ThreadSnapshotV3 {
  if (event.type === 'thread.snapshot.v3') {
    return event.payload.snapshot
  }

  if (!snapshot) {
    throw new ThreadEventApplyErrorV3(
      'missing_snapshot',
      'Received a thread V3 event before a snapshot was available.',
    )
  }

  const nextSnapshotVersion = event.snapshotVersion ?? snapshot.snapshotVersion
  const nextUpdatedAt = event.occurredAt ?? snapshot.updatedAt

  switch (event.type) {
    case 'conversation.item.upsert.v3': {
      const normalized = normalizeSnapshot(snapshot)
      const operationKind = classifyThreadEventOperationV3(snapshot, event) ?? 'patch-meta'
      const incomingItem = event.payload.item
      const existingItem = normalized.itemsById[incomingItem.id]

      let nextItemsById = normalized.itemsById
      if (existingItem !== incomingItem) {
        nextItemsById = {
          ...normalized.itemsById,
          [incomingItem.id]: incomingItem,
        }
      }

      let nextOrderedItemIds = normalized.orderedItemIds
      if (operationKind === 'insert') {
        nextOrderedItemIds = [...normalized.orderedItemIds, incomingItem.id]
      }
      if (operationKind === 'insert' || operationKind === 'reorder') {
        nextOrderedItemIds = sortOrderedItemIds(nextItemsById, nextOrderedItemIds)
      }

      return materializeSnapshot(snapshot, {
        ...normalized,
        itemsById: nextItemsById,
        orderedItemIds: nextOrderedItemIds,
        snapshotVersion: nextSnapshotVersion,
        updatedAt: incomingItem.updatedAt || nextUpdatedAt,
      })
    }

    case 'conversation.item.patch.v3': {
      const patch = event.payload.patch
      if (patch.kind === 'message') {
        const fastSnapshot = tryApplyFastMessageAppendPatch(
          snapshot,
          event.payload.itemId,
          patch as MessagePatchV3,
          {
            nextSnapshotVersion,
            nextUpdatedAt,
            diagnostics,
          },
        )
        if (fastSnapshot) {
          return fastSnapshot
        }
      }

      const normalized = normalizeSnapshot(snapshot)
      const target = normalized.itemsById[event.payload.itemId]
      if (!target) {
        throw new ThreadEventApplyErrorV3(
          'missing_item',
          `Cannot patch missing conversation item ${event.payload.itemId}.`,
        )
      }

      let nextItem: ConversationItemV3
      if (patch.kind === 'message') {
        const messagePatch = patch as MessagePatchV3
        if (
          target.kind === 'message' &&
          isAppendSafeMessagePatch(messagePatch) &&
          typeof messagePatch.textAppend === 'string' &&
          messagePatch.textAppend.length > 0
        ) {
          nextItem = {
            ...target,
            text: `${target.text}${messagePatch.textAppend}`,
            status: messagePatch.status ?? target.status,
            updatedAt: messagePatch.updatedAt,
          }
          markFastAppendUsed(diagnostics)
        } else {
          if (typeof messagePatch.textAppend === 'string') {
            markFastAppendFallback(diagnostics)
          }
          nextItem = applyItemPatch(target, patch)
        }
      } else {
        nextItem = applyItemPatch(target, patch)
      }

      const nextItemsById =
        nextItem === target
          ? normalized.itemsById
          : {
              ...normalized.itemsById,
              [event.payload.itemId]: nextItem,
            }

      return materializeSnapshot(snapshot, {
        ...normalized,
        itemsById: nextItemsById,
        snapshotVersion: nextSnapshotVersion,
        updatedAt: patch.updatedAt,
      })
    }

    case 'thread.lifecycle.v3':
      return {
        ...snapshot,
        activeTurnId: event.payload.activeTurnId,
        processingState: event.payload.processingState,
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }

    case 'conversation.ui.plan_ready.v3': {
      const nextPlanReady = event.payload.planReady
      const currentPlanReady = snapshot.uiSignals.planReady
      const planReady = arePlanReadySignalsEqual(currentPlanReady, nextPlanReady)
        ? currentPlanReady
        : nextPlanReady
      const nextUiSignals =
        planReady === currentPlanReady
          ? snapshot.uiSignals
          : {
              ...snapshot.uiSignals,
              planReady,
            }

      return {
        ...snapshot,
        uiSignals: nextUiSignals,
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }
    }

    case 'conversation.ui.user_input.v3': {
      const currentRequests = snapshot.uiSignals.activeUserInputRequests
      const nextRequests = event.payload.activeUserInputRequests
      const mergedRequests = arePendingUserInputRequestsEqual(currentRequests, nextRequests)
        ? currentRequests
        : nextRequests
      const nextUiSignals =
        mergedRequests === currentRequests
          ? snapshot.uiSignals
          : {
              ...snapshot.uiSignals,
              activeUserInputRequests: mergedRequests,
            }
      return {
        ...snapshot,
        uiSignals: nextUiSignals,
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }
    }

    case 'thread.error.v3':
      return {
        ...snapshot,
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }

    default:
      return snapshot
  }
}
