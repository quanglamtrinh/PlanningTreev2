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
  UserInputItemV3,
  UserInputPatchV3,
  ConversationMessageItemV3,
} from '../../../api/types'

export class ThreadEventApplyErrorV3 extends Error {
  code: 'missing_snapshot' | 'missing_item' | 'kind_mismatch'

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

function sortItems(items: ConversationItemV3[]): ConversationItemV3[] {
  return [...items].sort((left, right) => {
    if (left.sequence !== right.sequence) {
      return left.sequence - right.sequence
    }
    return left.createdAt.localeCompare(right.createdAt)
  })
}

function upsertItem(items: ConversationItemV3[], item: ConversationItemV3): ConversationItemV3[] {
  const next = [...items]
  const existingIndex = next.findIndex((candidate) => candidate.id === item.id)
  if (existingIndex >= 0) {
    next[existingIndex] = item
  } else {
    next.push(item)
  }
  return sortItems(next)
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
    default:
      return item
  }
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
    case 'conversation.item.upsert.v3':
      return {
        ...snapshot,
        items: upsertItem(snapshot.items, event.payload.item),
        snapshotVersion: nextSnapshotVersion,
        updatedAt: event.payload.item.updatedAt || nextUpdatedAt,
      }

    case 'conversation.item.patch.v3': {
      const index = snapshot.items.findIndex((item) => item.id === event.payload.itemId)
      if (index < 0) {
        throw new ThreadEventApplyErrorV3(
          'missing_item',
          `Cannot patch missing conversation item ${event.payload.itemId}.`,
        )
      }
      if (event.payload.patch.kind === 'message') {
        const patch = event.payload.patch
        const target = snapshot.items[index]
        const patchRecord = patch as unknown as Record<string, unknown>
        const patchKeys = Object.keys(patchRecord)
        const isAppendSafePatch = patchKeys.every((key) =>
          key === 'kind' || key === 'textAppend' || key === 'status' || key === 'updatedAt',
        )
        if (
          target.kind === 'message' &&
          isAppendSafePatch &&
          typeof patch.textAppend === 'string' &&
          patch.textAppend.length > 0
        ) {
          const nextItems = [...snapshot.items]
          nextItems[index] = {
            ...target,
            text: `${target.text}${patch.textAppend}`,
            status: patch.status ?? target.status,
            updatedAt: patch.updatedAt,
          }
          markFastAppendUsed(diagnostics)
          return {
            ...snapshot,
            items: nextItems,
            snapshotVersion: nextSnapshotVersion,
            updatedAt: patch.updatedAt,
          }
        }
        if (typeof patch.textAppend === 'string') {
          markFastAppendFallback(diagnostics)
        }
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

    case 'thread.lifecycle.v3':
      return {
        ...snapshot,
        activeTurnId: event.payload.activeTurnId,
        processingState: event.payload.processingState,
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }

    case 'conversation.ui.plan_ready.v3':
      return {
        ...snapshot,
        uiSignals: {
          ...snapshot.uiSignals,
          planReady: event.payload.planReady,
        },
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
      }

    case 'conversation.ui.user_input.v3':
      return {
        ...snapshot,
        uiSignals: {
          ...snapshot.uiSignals,
          activeUserInputRequests: event.payload.activeUserInputRequests,
        },
        snapshotVersion: nextSnapshotVersion,
        updatedAt: nextUpdatedAt,
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
