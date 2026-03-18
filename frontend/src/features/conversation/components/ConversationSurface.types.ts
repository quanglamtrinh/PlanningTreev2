import type { KeyboardEvent, ReactNode } from 'react'

import type { RuntimeInputAnswer } from '../../../api/types'
import type { ActiveConversationRequest } from '../hooks/useConversationRequests'
import type { ConversationRenderModel } from '../model/buildConversationRenderModel'

export type ConversationSurfaceConnectionState =
  | 'idle'
  | 'loading'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'error'

export type ConversationSurfaceVariant = 'minimal' | 'codex_execution'

export interface ConversationSurfaceMessageAction {
  key: string
  label: string
  disabled?: boolean
  onPress: () => void
}

export interface ConversationSurfaceTranscriptStatus {
  isStreaming: boolean
  startedAt?: number | null
  lastDurationMs?: number | null
  workingLabel?: string | null
}

export interface ConversationSurfaceRequestUi {
  isSubmitting: boolean
  error: string | null
  submitUserInputResponse: (args: {
    requestId: string
    threadId?: string | null
    turnId?: string | null
    answers: Record<string, RuntimeInputAnswer>
  }) => Promise<unknown>
  respondToApproval: (args: {
    requestId: string
    decision: 'approved' | 'declined'
    threadId?: string | null
    turnId?: string | null
  }) => Promise<unknown>
}

export interface ConversationSurfaceProps {
  model: ConversationRenderModel | null
  connectionState: ConversationSurfaceConnectionState
  isLoading: boolean
  errorMessage: string | null
  contextLabel?: string
  emptyTitle: string
  emptyHint: ReactNode
  showHeader?: boolean
  showComposer?: boolean
  composerValue?: string
  composerDisabled?: boolean
  composerPlaceholder?: string
  composerHint?: ReactNode
  onComposerValueChange?: (draft: string) => void
  onComposerSubmit?: () => void
  onComposerKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void
  messageActions?: Record<string, ConversationSurfaceMessageAction[]>
  streamAction?: {
    label: string
    disabled?: boolean
    onPress: () => void
  } | null
  variant?: ConversationSurfaceVariant
  onQuoteMessage?: (quotedMarkdown: string) => void
  canStop?: boolean
  onStop?: () => void
  transcriptStatus?: ConversationSurfaceTranscriptStatus | null
  activeRequest?: ActiveConversationRequest | null
  requestUi?: ConversationSurfaceRequestUi | null
}
