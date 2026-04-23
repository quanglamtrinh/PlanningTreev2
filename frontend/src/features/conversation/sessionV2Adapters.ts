import type {
  ConversationItemV3,
  ThreadSnapshotV3,
  UserInputItemV3,
  UserInputQuestionOptionV3,
  UserInputQuestionV3,
  UserInputAnswer,
} from '../../api/types'
import type { PendingServerRequest, SessionItem, SessionTurn } from '../session_v2/contracts'
import type {
  BreadcrumbSessionUiAdapter,
  BreadcrumbV3ComposerSource,
  BreadcrumbV3PendingRequestSource,
  BreadcrumbV3TranscriptSource,
} from './sessionV2AdapterContracts'

const ORPHAN_TURN_ID = '_orphan'

function normalizeText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function normalizeNonEmptyString(value: unknown): string | null {
  const text = normalizeText(value)
  return text.length > 0 ? text : null
}

function parseTimestampMs(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value) && value >= 0) {
    return value
  }
  if (typeof value === 'string') {
    const parsed = Date.parse(value)
    if (Number.isFinite(parsed) && parsed >= 0) {
      return parsed
    }
  }
  return null
}

function resolveTimestampMs(value: unknown, fallback: number): number {
  return parseTimestampMs(value) ?? fallback
}

function mapItemStatus(status: ConversationItemV3['status']): SessionItem['status'] {
  if (status === 'pending' || status === 'in_progress' || status === 'requested' || status === 'answer_submitted') {
    return 'inProgress'
  }
  if (status === 'completed' || status === 'answered') {
    return 'completed'
  }
  return 'failed'
}

function mapProcessingStateToTurnStatus(
  processingState: ThreadSnapshotV3['processingState'],
): SessionTurn['status'] {
  if (processingState === 'running') {
    return 'inProgress'
  }
  if (processingState === 'waiting_user_input') {
    return 'waitingUserInput'
  }
  if (processingState === 'failed') {
    return 'failed'
  }
  return 'completed'
}

function mapTurnStatusToCodexStatus(
  status: SessionTurn['status'],
): SessionTurn['lastCodexStatus'] {
  if (status === 'waitingUserInput' || status === 'inProgress') {
    return 'inProgress'
  }
  if (status === 'completed') {
    return 'completed'
  }
  if (status === 'failed') {
    return 'failed'
  }
  if (status === 'interrupted') {
    return 'interrupted'
  }
  return null
}

function mapFileChangeKind(
  changeType: 'created' | 'updated' | 'deleted' | null | undefined,
): 'add' | 'modify' | 'delete' {
  if (changeType === 'created') {
    return 'add'
  }
  if (changeType === 'deleted') {
    return 'delete'
  }
  return 'modify'
}

function buildUserInputQuestionsPayload(questions: UserInputQuestionV3[]): Array<Record<string, unknown>> {
  return questions.map((question) => ({
    id: question.id,
    question: question.prompt,
    options: question.options.map((option) => ({
      label: option.label,
      description: option.description,
      value: option.label,
    })),
  }))
}

function buildUserInputAnswerSummary(answers: UserInputAnswer[]): string {
  if (answers.length === 0) {
    return 'No answers yet.'
  }
  return answers
    .map((answer) => `${answer.questionId}: ${answer.label ?? answer.value}`)
    .join('\n')
}

function mapItemToSession(
  item: ConversationItemV3,
  threadId: string,
  turnId: string,
): SessionItem {
  const now = Date.now()
  const createdAtMs = resolveTimestampMs(item.createdAt, now)
  const updatedAtMs = resolveTimestampMs(item.updatedAt, createdAtMs)
  const status = mapItemStatus(item.status)

  if (item.kind === 'message') {
    if (item.role === 'user') {
      return {
        id: item.id,
        threadId,
        turnId,
        kind: 'userMessage',
        status,
        createdAtMs,
        updatedAtMs,
        payload: {
          type: 'userMessage',
          role: item.role,
          text: item.text,
          content: [{ type: 'text', text: item.text }],
          metadata: item.metadata,
        },
      }
    }
    return {
      id: item.id,
      threadId,
      turnId,
      kind: 'agentMessage',
      status,
      createdAtMs,
      updatedAtMs,
      payload: {
        type: 'agentMessage',
        role: item.role,
        text: item.text,
        metadata: item.metadata,
      },
    }
  }

  if (item.kind === 'reasoning') {
    return {
      id: item.id,
      threadId,
      turnId,
      kind: 'reasoning',
      status,
      createdAtMs,
      updatedAtMs,
      payload: {
        type: 'reasoning',
        summary: item.summaryText ? [item.summaryText] : [],
        content: item.detailText ? [item.detailText] : [],
        metadata: item.metadata,
      },
    }
  }

  if (item.kind === 'tool') {
    if (item.toolType === 'fileChange') {
      return {
        id: item.id,
        threadId,
        turnId,
        kind: 'fileChange',
        status,
        createdAtMs,
        updatedAtMs,
        payload: {
          type: 'fileChange',
          output: item.outputText,
          changes: item.outputFiles.map((output) => ({
            path: output.path,
            kind: output.kind ?? mapFileChangeKind(output.changeType),
            summary: output.summary,
            diff: output.diff ?? null,
          })),
          metadata: item.metadata,
        },
      }
    }
    return {
      id: item.id,
      threadId,
      turnId,
      kind: 'commandExecution',
      status,
      createdAtMs,
      updatedAtMs,
      payload: {
        type: 'commandExecution',
        command: item.title || item.toolName || 'command',
        aggregatedOutput: item.outputText,
        output: item.outputText,
        argumentsText: item.argumentsText,
        callId: item.callId,
        exitCode: item.exitCode,
        metadata: item.metadata,
      },
    }
  }

  if (item.kind === 'diff') {
    return {
      id: item.id,
      threadId,
      turnId,
      kind: 'fileChange',
      status,
      createdAtMs,
      updatedAtMs,
      payload: {
        type: 'fileChange',
        output: item.summaryText ?? '',
        changes: item.changes.map((change) => ({
          path: change.path,
          kind: change.kind,
          summary: change.summary,
          diff: change.diff,
        })),
        files: item.files.map((file) => ({
          path: file.path,
          kind: mapFileChangeKind(file.changeType),
          summary: file.summary,
          diff: file.patchText,
        })),
        metadata: item.metadata,
      },
    }
  }

  if (item.kind === 'error') {
    return {
      id: item.id,
      threadId,
      turnId,
      kind: 'error',
      status,
      createdAtMs,
      updatedAtMs,
      payload: {
        type: 'error',
        title: item.title,
        text: item.message,
        code: item.code,
        recoverable: item.recoverable,
        metadata: item.metadata,
      },
    }
  }

  if (item.kind === 'userInput') {
    return {
      id: item.id,
      threadId,
      turnId,
      kind: 'userInput',
      status,
      createdAtMs,
      updatedAtMs,
      payload: {
        type: 'userInput',
        title: item.title,
        text: buildUserInputAnswerSummary(item.answers),
        requestId: item.requestId,
        questions: buildUserInputQuestionsPayload(item.questions),
        answers: item.answers.map((answer) => ({
          questionId: answer.questionId,
          value: answer.value,
          label: answer.label,
        })),
        metadata: item.metadata,
      },
    }
  }

  if (item.kind === 'explore') {
    return {
      id: item.id,
      threadId,
      turnId,
      kind: 'agentMessage',
      status,
      createdAtMs,
      updatedAtMs,
      payload: {
        type: 'agentMessage',
        text: [item.title, item.text].filter(Boolean).join('\n'),
        metadata: item.metadata,
      },
    }
  }

  if (item.kind === 'review') {
    const disposition = item.disposition ? `Disposition: ${item.disposition}` : null
    return {
      id: item.id,
      threadId,
      turnId,
      kind: 'agentMessage',
      status,
      createdAtMs,
      updatedAtMs,
      payload: {
        type: 'agentMessage',
        text: [item.title, item.text, disposition].filter(Boolean).join('\n'),
        metadata: item.metadata,
      },
    }
  }

  if (item.kind === 'status') {
    return {
      id: item.id,
      threadId,
      turnId,
      kind: 'agentMessage',
      status,
      createdAtMs,
      updatedAtMs,
      payload: {
        type: 'agentMessage',
        text: [item.label, item.detail].filter(Boolean).join('\n'),
        code: item.code,
        metadata: item.metadata,
      },
    }
  }

  throw new Error(`Unsupported conversation item kind: ${(item as { kind: string }).kind}`)
}

function parsePendingRequestStatus(status: string): PendingServerRequest['status'] {
  if (status === 'answer_submitted') {
    return 'submitted'
  }
  if (status === 'answered') {
    return 'resolved'
  }
  if (status === 'stale') {
    return 'expired'
  }
  return 'pending'
}

function mapQuestionOptions(
  options: UserInputQuestionOptionV3[],
): Array<Record<string, unknown>> {
  return options.map((option) => ({
    label: option.label,
    description: option.description,
    value: option.label,
  }))
}

function mapQuestionsForPendingRequest(
  item: UserInputItemV3 | null,
): Array<Record<string, unknown>> {
  if (!item) {
    return []
  }
  return item.questions.map((question) => ({
    id: question.id,
    question: question.prompt,
    options: mapQuestionOptions(question.options),
  }))
}

function serializeComposerInput(input: Array<Record<string, unknown>>, fallbackText: string): string {
  const rows: string[] = []
  for (const item of input) {
    if (!item || typeof item !== 'object') {
      continue
    }
    const record = item as Record<string, unknown>
    const type = normalizeText(record.type)
    if (type === 'text') {
      const text = normalizeText(record.text)
      if (text) {
        rows.push(text)
      }
      continue
    }
    if (type === 'image') {
      const imageUrl = normalizeText(record.imageUrl)
      if (imageUrl) {
        rows.push(`[Image] ${imageUrl}`)
      }
      continue
    }
    if (type === 'localImage') {
      const path = normalizeText(record.path)
      if (path) {
        rows.push(`[Local image] ${path}`)
      }
      continue
    }
    const text = normalizeText(record.text)
    if (text) {
      rows.push(text)
    }
  }
  const serialized = rows.join('\n').trim()
  if (serialized.length > 0) {
    return serialized
  }
  return normalizeText(fallbackText)
}

function parseQuestionOptions(
  questionRecord: Record<string, unknown>,
): Array<{ label: string; value: string }> {
  const options = Array.isArray(questionRecord.options) ? questionRecord.options : []
  const parsed: Array<{ label: string; value: string }> = []
  for (const option of options) {
    if (!option || typeof option !== 'object') {
      continue
    }
    const optionRecord = option as Record<string, unknown>
    const label = normalizeText(optionRecord.label)
    const value = normalizeText(optionRecord.value) || label
    if (!label || !value) {
      continue
    }
    parsed.push({ label, value })
  }
  return parsed
}

function buildQuestionOptionMap(
  request: PendingServerRequest,
): Map<string, Array<{ label: string; value: string }>> {
  const map = new Map<string, Array<{ label: string; value: string }>>()
  const questions = Array.isArray(request.payload.questions) ? request.payload.questions : []
  for (const question of questions) {
    if (!question || typeof question !== 'object') {
      continue
    }
    const record = question as Record<string, unknown>
    const questionId = normalizeText(record.id)
    if (!questionId) {
      continue
    }
    map.set(questionId, parseQuestionOptions(record))
  }
  return map
}

const transcriptAdapter: BreadcrumbSessionUiAdapter<
  BreadcrumbV3TranscriptSource,
  BreadcrumbV3ComposerSource,
  BreadcrumbV3PendingRequestSource
>['transcript'] = {
  toTranscriptModel(source, context) {
    const snapshot = source.snapshot
    const threadId = context.activeThreadId ?? snapshot?.threadId ?? null
    if (!snapshot || !threadId) {
      return {
        threadId,
        turns: [],
        itemsByTurn: {},
      }
    }

    const sortedItems = [...snapshot.items].sort((left, right) => {
      if (left.sequence !== right.sequence) {
        return left.sequence - right.sequence
      }
      const leftCreated = resolveTimestampMs(left.createdAt, 0)
      const rightCreated = resolveTimestampMs(right.createdAt, 0)
      if (leftCreated !== rightCreated) {
        return leftCreated - rightCreated
      }
      return left.id.localeCompare(right.id)
    })

    const turnOrder: string[] = []
    const itemsByTurnId = new Map<string, SessionItem[]>()
    for (const item of sortedItems) {
      const normalizedTurnId = normalizeNonEmptyString(item.turnId) ?? ORPHAN_TURN_ID
      if (!itemsByTurnId.has(normalizedTurnId)) {
        itemsByTurnId.set(normalizedTurnId, [])
        turnOrder.push(normalizedTurnId)
      }
      const mapped = mapItemToSession(item, threadId, normalizedTurnId)
      itemsByTurnId.get(normalizedTurnId)?.push(mapped)
    }

    const activeTurnId = normalizeNonEmptyString(snapshot.activeTurnId)
    if (activeTurnId && !itemsByTurnId.has(activeTurnId)) {
      itemsByTurnId.set(activeTurnId, [])
      turnOrder.push(activeTurnId)
    }

    const snapshotCreatedAtMs = resolveTimestampMs(snapshot.createdAt, Date.now())
    const snapshotUpdatedAtMs = resolveTimestampMs(snapshot.updatedAt, snapshotCreatedAtMs)
    const turns: SessionTurn[] = turnOrder.map((turnId) => {
      const turnItems = itemsByTurnId.get(turnId) ?? []
      const isActiveTurn = activeTurnId === turnId
      const status = isActiveTurn
        ? mapProcessingStateToTurnStatus(snapshot.processingState)
        : 'completed'
      const startedAtMs =
        turnItems.length > 0
          ? Math.min(...turnItems.map((entry) => entry.createdAtMs))
          : snapshotCreatedAtMs
      const completedAtMs =
        status === 'inProgress' || status === 'waitingUserInput'
          ? null
          : turnItems.length > 0
            ? Math.max(...turnItems.map((entry) => entry.updatedAtMs))
            : snapshotUpdatedAtMs
      const errorItem = [...turnItems]
        .reverse()
        .find((entry) => entry.kind === 'error')
      const errorMessage = errorItem
        ? normalizeText(errorItem.payload.text ?? errorItem.payload.message) || 'Turn failed.'
        : 'Turn failed.'

      return {
        id: turnId,
        threadId,
        status,
        lastCodexStatus: mapTurnStatusToCodexStatus(status),
        startedAtMs,
        completedAtMs,
        items: turnItems,
        error:
          status === 'failed'
            ? {
                code: 'ERR_INTERNAL',
                message: errorMessage,
              }
            : null,
      }
    })

    const itemsByTurn: Record<string, SessionItem[]> = {}
    for (const turn of turns) {
      itemsByTurn[`${threadId}:${turn.id}`] = turn.items
    }

    return {
      threadId,
      turns,
      itemsByTurn,
    }
  },
}

const composerAdapter: BreadcrumbSessionUiAdapter<
  BreadcrumbV3TranscriptSource,
  BreadcrumbV3ComposerSource,
  BreadcrumbV3PendingRequestSource
>['composer'] = {
  capabilities: {
    supportsInterrupt: false,
    supportsImageInput: true,
    supportsLocalImageInput: true,
    supportsModelPicker: true,
  },
  toComposerModel(source) {
    return {
      isTurnRunning: false,
      disabled: source.disabled,
      async onSubmit(payload) {
        const text = serializeComposerInput(payload.input, payload.text)
        if (!text) {
          return
        }
        await source.submitText(text)
      },
      async onInterrupt() {
        return
      },
      currentCwd: source.currentCwd ?? null,
      modelOptions: source.modelOptions,
      selectedModel: source.selectedModel ?? null,
      onModelChange: source.onModelChange,
      isModelLoading: source.isModelLoading,
    }
  },
}

const pendingRequestAdapter: BreadcrumbSessionUiAdapter<
  BreadcrumbV3TranscriptSource,
  BreadcrumbV3ComposerSource,
  BreadcrumbV3PendingRequestSource
>['pendingRequest'] = {
  toPendingRequest(source, context) {
    const snapshot = source.snapshot
    const threadId = context.activeThreadId ?? snapshot?.threadId ?? null
    if (!snapshot || !threadId) {
      return null
    }
    const request = snapshot.uiSignals.activeUserInputRequests.find(
      (candidate) =>
        candidate.status === 'requested' || candidate.status === 'answer_submitted',
    )
    if (!request) {
      return null
    }
    const requestItem = snapshot.items.find(
      (item): item is UserInputItemV3 =>
        item.kind === 'userInput' && item.requestId === request.requestId,
    ) ?? null
    const createdAtMs = resolveTimestampMs(request.createdAt, Date.now())
    return {
      requestId: request.requestId,
      method: 'item/tool/requestUserInput',
      threadId,
      turnId: request.turnId ?? requestItem?.turnId ?? null,
      itemId: request.itemId ?? requestItem?.id ?? null,
      status: parsePendingRequestStatus(request.status),
      createdAtMs,
      submittedAtMs: parseTimestampMs(request.submittedAt),
      resolvedAtMs: parseTimestampMs(request.resolvedAt),
      payload: {
        requestId: request.requestId,
        title: requestItem?.title ?? null,
        questions: mapQuestionsForPendingRequest(requestItem),
        answers: requestItem?.answers ?? request.answers ?? [],
      },
    }
  },
  toUserInputAnswers(request, result) {
    const optionMapByQuestion = buildQuestionOptionMap(request)
    const rawAnswers = Array.isArray(result.answers) ? result.answers : []
    const answers: UserInputAnswer[] = []

    for (const raw of rawAnswers) {
      if (!raw || typeof raw !== 'object') {
        continue
      }
      const record = raw as Record<string, unknown>
      const questionId = normalizeText(record.id)
      if (!questionId) {
        continue
      }
      const selectedOption = normalizeText(record.selectedOption)
      const notes = normalizeText(record.notes)
      const options = optionMapByQuestion.get(questionId) ?? []
      if (selectedOption) {
        const matchedOption = options.find(
          (option) => option.value === selectedOption || option.label === selectedOption,
        )
        answers.push({
          questionId,
          value: matchedOption?.value ?? selectedOption,
          label: matchedOption?.label ?? null,
        })
        continue
      }
      if (notes) {
        answers.push({
          questionId,
          value: notes,
          label: null,
        })
      }
    }

    return answers
  },
}

export const breadcrumbV3SessionUiAdapter: BreadcrumbSessionUiAdapter<
  BreadcrumbV3TranscriptSource,
  BreadcrumbV3ComposerSource,
  BreadcrumbV3PendingRequestSource
> = {
  transcript: transcriptAdapter,
  composer: composerAdapter,
  pendingRequest: pendingRequestAdapter,
}
