import { useEffect, useMemo, useRef, useState } from 'react'

import { api } from '../../../api/client'
import type { RuntimeInputAnswer } from '../../../api/types'
import type {
  ConversationMessage,
  ConversationMessagePart,
  ConversationSnapshot,
} from '../types'

export type ConversationRequestKind = 'approval' | 'user_input'

export interface ConversationRequestOption {
  label: string
  description: string
}

export interface ConversationRequestQuestion {
  id: string
  header: string
  question: string
  isOther: boolean
  isSecret: boolean
  options: ConversationRequestOption[]
}

export interface ActiveConversationRequest {
  requestId: string
  requestKind: ConversationRequestKind
  resolutionState: string
  messageId: string
  partId: string
  threadId: string | null
  turnId: string | null
  itemId: string | null
  title: string | null
  summary: string | null
  prompt: string | null
  questions: ConversationRequestQuestion[]
}

type UseConversationRequestsOptions = {
  projectId: string | null
  nodeId: string | null
  conversation: { snapshot: ConversationSnapshot } | null
  refresh?: (() => void) | null
}

type SubmitUserInputResponseArgs = {
  requestId: string
  threadId?: string | null
  turnId?: string | null
  answers: Record<string, RuntimeInputAnswer>
}

type RespondToApprovalArgs = {
  requestId: string
  decision: 'approved' | 'declined'
  threadId?: string | null
  turnId?: string | null
}

type UseConversationRequestsResult = {
  activeRequest: ActiveConversationRequest | null
  pendingRequestCount: number
  isSubmitting: boolean
  submitError: string | null
  submitUserInputResponse: (args: SubmitUserInputResponseArgs) => Promise<'resolved' | 'already_resolved_or_stale'>
  respondToApproval: (args: RespondToApprovalArgs) => Promise<'resolved' | 'already_resolved_or_stale'>
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

function asArray(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null
}

function sortParts(parts: ConversationMessagePart[]): ConversationMessagePart[] {
  return [...parts].sort(
    (left, right) => left.order - right.order || left.part_id.localeCompare(right.part_id),
  )
}

function isUnresolvedRequest(part: ConversationMessagePart): boolean {
  if (part.part_type !== 'approval_request' && part.part_type !== 'user_input_request') {
    return false
  }
  const resolutionState = asString(part.payload.resolution_state) ?? 'pending'
  return resolutionState === 'pending'
}

function normalizeQuestions(rawQuestions: unknown): ConversationRequestQuestion[] {
  const questions = asArray(rawQuestions)
  if (!questions) {
    return []
  }
  return questions.flatMap((entry) => {
    const question = asRecord(entry)
    if (!question) {
      return []
    }
    const id = asString(question.id)
    const header = asString(question.header)
    const body = asString(question.question)
    if (!id || !header || !body) {
      return []
    }
    const options = (asArray(question.options) ?? []).flatMap((option) => {
      const typedOption = asRecord(option)
      const label = typedOption ? asString(typedOption.label) : null
      if (!label) {
        return []
      }
      return [
        {
          label,
          description: asString(typedOption?.description) ?? '',
        },
      ]
    })
    return [
      {
        id,
        header,
        question: body,
        isOther: Boolean(question.is_other),
        isSecret: Boolean(question.is_secret),
        options,
      },
    ]
  })
}

function toActiveConversationRequest(
  message: ConversationMessage,
  part: ConversationMessagePart,
): ActiveConversationRequest | null {
  if (part.part_type !== 'approval_request' && part.part_type !== 'user_input_request') {
    return null
  }
  const requestId = asString(part.payload.request_id)
  if (!requestId) {
    return null
  }
  return {
    requestId,
    requestKind: part.part_type === 'approval_request' ? 'approval' : 'user_input',
    resolutionState: asString(part.payload.resolution_state) ?? 'pending',
    messageId: message.message_id,
    partId: part.part_id,
    threadId: asString(part.payload.thread_id),
    turnId: asString(part.payload.turn_id) ?? message.turn_id,
    itemId: asString(part.payload.item_id),
    title: asString(part.payload.title),
    summary: asString(part.payload.summary),
    prompt: asString(part.payload.prompt) ?? asString(part.payload.details),
    questions: normalizeQuestions(part.payload.questions),
  }
}

export function deriveConversationRequests(snapshot: ConversationSnapshot | null | undefined): {
  activeRequest: ActiveConversationRequest | null
  pendingRequestCount: number
} {
  if (!snapshot) {
    return {
      activeRequest: null,
      pendingRequestCount: 0,
    }
  }

  let activeRequest: ActiveConversationRequest | null = null
  let pendingRequestCount = 0

  for (const message of snapshot.messages) {
    for (const part of sortParts(message.parts)) {
      if (!isUnresolvedRequest(part)) {
        continue
      }
      const parsed = toActiveConversationRequest(message, part)
      if (!parsed) {
        continue
      }
      pendingRequestCount += 1
      activeRequest = parsed
    }
  }

  return {
    activeRequest,
    pendingRequestCount,
  }
}

export function useConversationRequests({
  projectId,
  nodeId,
  conversation,
  refresh,
}: UseConversationRequestsOptions): UseConversationRequestsResult {
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submittingRequestId, setSubmittingRequestId] = useState<string | null>(null)
  const conversationRef = useRef(conversation)
  const refreshRef = useRef(refresh ?? null)

  useEffect(() => {
    conversationRef.current = conversation
  }, [conversation])

  useEffect(() => {
    refreshRef.current = refresh ?? null
  }, [refresh])

  const requestState = useMemo(
    () => deriveConversationRequests(conversation?.snapshot ?? null),
    [conversation?.snapshot],
  )

  useEffect(() => {
    if (submittingRequestId && requestState.activeRequest?.requestId !== submittingRequestId) {
      setSubmittingRequestId(null)
    }
  }, [requestState.activeRequest?.requestId, submittingRequestId])

  async function guardedRefreshIfStillActive(requestId: string) {
    await new Promise((resolve) => {
      globalThis.setTimeout(resolve, 350)
    })
    const current = conversationRef.current?.snapshot ?? null
    const latest = deriveConversationRequests(current)
    if (latest.activeRequest?.requestId === requestId) {
      refreshRef.current?.()
    }
  }

  async function submitUserInputResponse(
    args: SubmitUserInputResponseArgs,
  ): Promise<'resolved' | 'already_resolved_or_stale'> {
    if (!projectId || !nodeId) {
      throw new Error('Conversation request resolution is not ready yet.')
    }
    setSubmittingRequestId(args.requestId)
    setSubmitError(null)
    try {
      const response = await api.resolveExecutionConversationRequest(projectId, nodeId, args.requestId, {
        request_kind: 'user_input',
        answers: args.answers,
        thread_id: args.threadId ?? null,
        turn_id: args.turnId ?? null,
      })
      void guardedRefreshIfStillActive(args.requestId)
      return response.status
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not resolve runtime input.'
      setSubmitError(message)
      setSubmittingRequestId(null)
      throw error
    }
  }

  async function respondToApproval(
    args: RespondToApprovalArgs,
  ): Promise<'resolved' | 'already_resolved_or_stale'> {
    if (!projectId || !nodeId) {
      throw new Error('Conversation approval resolution is not ready yet.')
    }
    setSubmittingRequestId(args.requestId)
    setSubmitError(null)
    try {
      const response = await api.resolveExecutionConversationRequest(projectId, nodeId, args.requestId, {
        request_kind: 'approval',
        decision: args.decision,
        thread_id: args.threadId ?? null,
        turn_id: args.turnId ?? null,
      })
      void guardedRefreshIfStillActive(args.requestId)
      return response.status
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Could not resolve approval request.'
      setSubmitError(message)
      setSubmittingRequestId(null)
      throw error
    }
  }

  return {
    activeRequest: requestState.activeRequest,
    pendingRequestCount: requestState.pendingRequestCount,
    isSubmitting: submittingRequestId !== null,
    submitError,
    submitUserInputResponse,
    respondToApproval,
  }
}
