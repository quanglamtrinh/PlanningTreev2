import type {
  ConversationMessage,
  ConversationMessagePart,
  ConversationMessageStatus,
  ConversationSnapshot,
} from '../types'

export type ConversationRenderRoleTone = 'user' | 'assistant' | 'neutral'

export type ConversationUnsupportedReason =
  | 'unknown_part_type'
  | 'unsupported_part_type'
  | 'malformed_payload'

interface ConversationRenderItemBase {
  key: string
  partId: string
  status: ConversationMessageStatus
}

export interface ConversationTextRenderItem extends ConversationRenderItemBase {
  kind: 'user_text' | 'assistant_text'
  text: string
}

export interface ConversationReasoningRenderItem extends ConversationRenderItemBase {
  kind: 'reasoning'
  title: string | null
  summary: string | null
  text: string | null
}

export interface ConversationToolCallRenderItem extends ConversationRenderItemBase {
  kind: 'tool_call'
  toolCallId: string | null
  toolName: string | null
  arguments: Record<string, unknown> | null
}

export interface ConversationToolResultRenderItem extends ConversationRenderItemBase {
  kind: 'tool_result'
  toolCallId: string | null
  text: string | null
  result: unknown
}

export interface ConversationPlanStepSummary {
  key: string
  title: string | null
  status: string | null
  description: string | null
}

export interface ConversationPlanBlockRenderItem extends ConversationRenderItemBase {
  kind: 'plan_block'
  planId: string | null
  title: string | null
  summary: string | null
  text: string | null
  steps: ConversationPlanStepSummary[]
}

export interface ConversationPlanStepUpdateRenderItem extends ConversationRenderItemBase {
  kind: 'plan_step_update'
  stepId: string | null
  title: string | null
  statusLabel: string | null
  text: string | null
}

export interface ConversationInteractiveQuestionSummary {
  key: string
  header: string | null
  question: string | null
  options: string[]
}

export interface ConversationApprovalRequestRenderItem extends ConversationRenderItemBase {
  kind: 'approval_request'
  requestId: string | null
  title: string | null
  summary: string | null
  prompt: string | null
  resolutionState: string | null
  decision: string | null
}

export interface ConversationUserInputRequestRenderItem extends ConversationRenderItemBase {
  kind: 'user_input_request'
  requestId: string | null
  title: string | null
  summary: string | null
  prompt: string | null
  resolutionState: string | null
  questions: ConversationInteractiveQuestionSummary[]
}

export interface ConversationInteractiveAnswerSummary {
  key: string
  label: string
  values: string[]
}

export interface ConversationUserInputResponseRenderItem extends ConversationRenderItemBase {
  kind: 'user_input_response'
  requestId: string | null
  title: string | null
  summary: string | null
  text: string | null
  answers: ConversationInteractiveAnswerSummary[]
}

export interface ConversationDiffSummaryRenderItem extends ConversationRenderItemBase {
  kind: 'diff_summary'
  title: string | null
  summary: string | null
  stats: {
    added: number | null
    removed: number | null
    changed: number | null
  }
  files: string[]
}

export interface ConversationFileChangeSummaryRenderItem extends ConversationRenderItemBase {
  kind: 'file_change_summary'
  filePath: string | null
  changeType: string | null
  summary: string | null
}

export interface ConversationUnsupportedRenderItem extends ConversationRenderItemBase {
  kind: 'unsupported'
  partType: string
  reason: ConversationUnsupportedReason
}

export type ConversationRenderItem =
  | ConversationTextRenderItem
  | ConversationReasoningRenderItem
  | ConversationToolCallRenderItem
  | ConversationToolResultRenderItem
  | ConversationPlanBlockRenderItem
  | ConversationPlanStepUpdateRenderItem
  | ConversationApprovalRequestRenderItem
  | ConversationUserInputRequestRenderItem
  | ConversationUserInputResponseRenderItem
  | ConversationDiffSummaryRenderItem
  | ConversationFileChangeSummaryRenderItem
  | ConversationUnsupportedRenderItem

export interface ConversationRenderMessage {
  messageId: string
  roleTone: ConversationRenderRoleTone
  items: ConversationRenderItem[]
  isStreaming: boolean
  hasError: boolean
  errorText?: string
  showTyping: boolean
}

export interface ConversationRenderModel {
  messages: ConversationRenderMessage[]
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return null
  }
  return value as Record<string, unknown>
}

function asString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asArray(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null
}

function readPrimaryText(payload: Record<string, unknown>): string | null {
  return (
    asString(payload.text) ??
    asString(payload.content) ??
    asString(payload.summary) ??
    asString(payload.title) ??
    null
  )
}

function toRoleTone(role: string): ConversationRenderRoleTone {
  if (role === 'user') {
    return 'user'
  }
  if (role === 'assistant') {
    return 'assistant'
  }
  return 'neutral'
}

function isStreamingStatus(status: ConversationMessage['status'] | ConversationMessagePart['status']): boolean {
  return status === 'pending' || status === 'streaming'
}

function sortParts(parts: ConversationMessagePart[]): ConversationMessagePart[] {
  return [...parts].sort(
    (left, right) => left.order - right.order || left.part_id.localeCompare(right.part_id),
  )
}

function makeUnsupportedItem(
  part: ConversationMessagePart,
  reason: ConversationUnsupportedReason,
): ConversationUnsupportedRenderItem {
  return {
    kind: 'unsupported',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    partType: part.part_type,
    reason,
  }
}

function appendRenderItem(
  items: ConversationRenderItem[],
  nextItem: ConversationRenderItem,
): ConversationRenderItem[] {
  const previous = items[items.length - 1] ?? null
  if (
    previous &&
    (previous.kind === 'assistant_text' || previous.kind === 'user_text') &&
    previous.kind === nextItem.kind &&
    (nextItem.kind === 'assistant_text' || nextItem.kind === 'user_text')
  ) {
    previous.text = `${previous.text}${nextItem.text}`
    previous.status =
      previous.status === 'streaming' || previous.status === 'pending' ? previous.status : nextItem.status
    return items
  }
  items.push(nextItem)
  return items
}

function buildReasoningItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const title = asString(payload.title)
  const summary = asString(payload.summary)
  const text = asString(payload.text) ?? asString(payload.content)
  if (!title && !summary && !text) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'reasoning',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    title,
    summary,
    text,
  }
}

function buildToolCallItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const argumentsPayload = asRecord(payload.arguments)
  const toolName = asString(payload.tool_name) ?? asString(payload.name)
  const toolCallId = asString(payload.tool_call_id) ?? asString(payload.call_id) ?? part.item_key
  if (!toolName && !argumentsPayload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'tool_call',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    toolCallId,
    toolName,
    arguments: argumentsPayload,
  }
}

function buildToolResultItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const toolCallId =
    asString(payload.tool_call_id) ??
    asString(payload.result_for_item_id) ??
    asString(payload.result_for_tool_call_id)
  const text = readPrimaryText(payload)
  const result = payload.output ?? payload.result ?? null
  if (!toolCallId && text === null && result === null) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'tool_result',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    toolCallId,
    text,
    result,
  }
}

function buildPlanSteps(value: unknown): ConversationPlanStepSummary[] {
  const steps = asArray(value)
  if (!steps) {
    return []
  }
  return steps.flatMap((entry, index) => {
    const step = asRecord(entry)
    if (!step) {
      return []
    }
    return [
      {
        key: asString(step.step_id) ?? asString(step.id) ?? `step-${index}`,
        title: asString(step.title) ?? asString(step.label) ?? asString(step.prompt),
        status: asString(step.status) ?? asString(step.state),
        description:
          asString(step.description) ??
          asString(step.summary) ??
          asString(step.definition_of_done) ??
          asString(step.content),
      },
    ]
  })
}

function buildPlanBlockItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const title = asString(payload.title)
  const summary = asString(payload.summary)
  const text = asString(payload.text) ?? asString(payload.content)
  const steps = buildPlanSteps(payload.steps)
  const planId = asString(payload.plan_id) ?? part.item_key
  if (!title && !summary && !text && steps.length === 0) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'plan_block',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    planId,
    title,
    summary,
    text,
    steps,
  }
}

function buildPlanStepUpdateItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const stepId = asString(payload.step_id) ?? part.item_key
  const title = asString(payload.title) ?? asString(payload.step_title) ?? asString(payload.label)
  const statusLabel = asString(payload.status) ?? asString(payload.state)
  const text =
    asString(payload.text) ?? asString(payload.content) ?? asString(payload.summary) ?? null
  if (!stepId && !title && !statusLabel && !text) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'plan_step_update',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    stepId,
    title,
    statusLabel,
    text,
  }
}

function buildInteractiveQuestions(value: unknown): ConversationInteractiveQuestionSummary[] {
  const questions = asArray(value)
  if (!questions) {
    return []
  }
  return questions.flatMap((entry, index) => {
    const question = asRecord(entry)
    if (!question) {
      return []
    }
    const optionsValue = asArray(question.options)
    const options =
      optionsValue?.flatMap((option) => {
        const typedOption = asRecord(option)
        const label = typedOption ? asString(typedOption.label) : typeof option === 'string' ? option : null
        return label ? [label] : []
      }) ?? []
    return [
      {
        key: asString(question.id) ?? `question-${index}`,
        header: asString(question.header),
        question: asString(question.question),
        options,
      },
    ]
  })
}

function buildInteractiveAnswers(value: unknown): ConversationInteractiveAnswerSummary[] {
  const answers = asRecord(value)
  if (!answers) {
    return []
  }
  return Object.entries(answers).flatMap(([key, entry]) => {
    const answerRecord = asRecord(entry)
    const rawAnswers = asArray(answerRecord?.answers)
    const values =
      rawAnswers?.flatMap((answer) => {
        const normalized = typeof answer === 'string' ? answer.trim() : ''
        return normalized ? [normalized] : []
      }) ?? []
    return [
      {
        key,
        label: key,
        values,
      },
    ]
  })
}

function buildApprovalRequestItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const requestId = asString(payload.request_id) ?? part.item_key
  const title = asString(payload.title)
  const summary = asString(payload.summary)
  const prompt = asString(payload.prompt) ?? asString(payload.details)
  const resolutionState = asString(payload.resolution_state)
  const decision = asString(payload.decision)
  if (!requestId && !title && !summary && !prompt) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'approval_request',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    requestId,
    title,
    summary,
    prompt,
    resolutionState,
    decision,
  }
}

function buildUserInputRequestItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const requestId = asString(payload.request_id) ?? part.item_key
  const title = asString(payload.title)
  const summary = asString(payload.summary)
  const prompt = asString(payload.prompt) ?? asString(payload.details)
  const resolutionState = asString(payload.resolution_state)
  const questions = buildInteractiveQuestions(payload.questions)
  if (!requestId && !title && !summary && !prompt && questions.length === 0) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'user_input_request',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    requestId,
    title,
    summary,
    prompt,
    resolutionState,
    questions,
  }
}

function buildUserInputResponseItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const requestId = asString(payload.request_id) ?? part.item_key
  const title = asString(payload.title)
  const summary = asString(payload.summary)
  const text = readPrimaryText(payload)
  const answers = buildInteractiveAnswers(payload.answers)
  if (!requestId && !title && !summary && !text && answers.length === 0) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'user_input_response',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    requestId,
    title,
    summary,
    text,
    answers,
  }
}

function readFileList(value: unknown): string[] {
  const files = asArray(value)
  if (!files) {
    return []
  }
  return files.flatMap((entry) => {
    if (typeof entry === 'string' && entry.trim()) {
      return [entry]
    }
    const record = asRecord(entry)
    if (!record) {
      return []
    }
    const filePath =
      asString(record.file_path) ??
      asString(record.path) ??
      asString(record.filename) ??
      asString(record.name)
    return filePath ? [filePath] : []
  })
}

function buildDiffSummaryItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const title = asString(payload.title)
  const summary = asString(payload.summary) ?? asString(payload.text) ?? asString(payload.content)
  const stats = {
    added: asNumber(payload.added),
    removed: asNumber(payload.removed),
    changed: asNumber(payload.changed),
  }
  const files = readFileList(payload.files)
  if (!title && !summary && files.length === 0 && !Object.values(stats).some((value) => value !== null)) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'diff_summary',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    title,
    summary,
    stats,
    files,
  }
}

function buildFileChangeSummaryItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  if (!payload) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  const filePath =
    asString(payload.file_path) ??
    asString(payload.path) ??
    asString(payload.filename) ??
    asString(payload.file_id)
  const changeType = asString(payload.change_type) ?? asString(payload.status)
  const summary = asString(payload.summary) ?? asString(payload.text) ?? asString(payload.content)
  if (!filePath && !changeType && !summary) {
    return makeUnsupportedItem(part, 'malformed_payload')
  }
  return {
    kind: 'file_change_summary',
    key: part.part_id,
    partId: part.part_id,
    status: part.status,
    filePath,
    changeType,
    summary,
  }
}

function buildRenderItem(part: ConversationMessagePart): ConversationRenderItem {
  const payload = asRecord(part.payload)
  switch (part.part_type) {
    case 'user_text':
    case 'assistant_text': {
      if (!payload) {
        return makeUnsupportedItem(part, 'malformed_payload')
      }
      const text = readPrimaryText(payload)
      if (text === null) {
        return makeUnsupportedItem(part, 'malformed_payload')
      }
      return {
        kind: part.part_type,
        key: part.part_id,
        partId: part.part_id,
        status: part.status,
        text,
      }
    }
    case 'reasoning':
      return buildReasoningItem(part)
    case 'tool_call':
      return buildToolCallItem(part)
    case 'tool_result':
      return buildToolResultItem(part)
    case 'plan_block':
      return buildPlanBlockItem(part)
    case 'plan_step_update':
      return buildPlanStepUpdateItem(part)
    case 'approval_request':
      return buildApprovalRequestItem(part)
    case 'user_input_request':
      return buildUserInputRequestItem(part)
    case 'user_input_response':
      return buildUserInputResponseItem(part)
    case 'diff_summary':
      return buildDiffSummaryItem(part)
    case 'file_change_summary':
      return buildFileChangeSummaryItem(part)
    case 'status_block':
      return makeUnsupportedItem(part, 'unsupported_part_type')
    default:
      return makeUnsupportedItem(part, 'unknown_part_type')
  }
}

function buildConversationRenderMessage(message: ConversationMessage): ConversationRenderMessage {
  const items = sortParts(message.parts).reduce<ConversationRenderItem[]>((acc, part) => {
    appendRenderItem(acc, buildRenderItem(part))
    return acc
  }, [])
  const roleTone = toRoleTone(message.role)
  const hasAssistantText = items.some(
    (item) => item.kind === 'assistant_text' && item.text.trim().length > 0,
  )
  const partStreaming = items.some((item) => isStreamingStatus(item.status))
  const partError = items.some((item) => item.status === 'error')
  const isStreaming = isStreamingStatus(message.status) || partStreaming
  const hasError = message.status === 'error' || partError || Boolean(message.error)

  return {
    messageId: message.message_id,
    roleTone,
    items,
    isStreaming,
    hasError,
    errorText: message.error ?? undefined,
    showTyping: roleTone === 'assistant' && isStreaming && !hasAssistantText,
  }
}

export function buildConversationRenderModel(
  snapshot: ConversationSnapshot | null | undefined,
): ConversationRenderModel | null {
  if (!snapshot) {
    return null
  }

  return {
    messages: snapshot.messages.map(buildConversationRenderMessage),
  }
}
