import type { ThreadSnapshotV3, UserInputAnswer } from '../../api/types'
import type { ComposerSubmitPayload } from '../session_v2/components/ComposerPane'
import type { PendingServerRequest, SessionItem, SessionTurn } from '../session_v2/contracts'
import type {
  StreamingTextLaneEntry,
  ThreadComposerState,
} from './state/threadByIdStoreV3'
import type { ThreadTab } from './surfaceRouting'

/**
 * Shared adapter context used by breadcrumb -> session_v2 bridges.
 *
 * The adapter layer must stay transport/session focused only:
 * - route/lane awareness for projection
 * - active thread identity for rendering
 * - no workflow transition or queue policy ownership
 */
export type BreadcrumbSessionAdapterContext = {
  threadTab: ThreadTab
  projectId: string | null
  nodeId: string | null
  activeThreadId: string | null
}

/**
 * Capability flags declared by an adapter implementation.
 * This helps callsites gate UX affordances without leaking implementation details.
 */
export type BreadcrumbSessionAdapterCapabilities = {
  supportsInterrupt: boolean
  supportsImageInput: boolean
  supportsLocalImageInput: boolean
  supportsModelPicker: boolean
}

/**
 * Target model for TranscriptPanel in session_v2.
 * Keep this shape aligned with `TranscriptPanel` props.
 */
export type BreadcrumbTranscriptAdapterModel = {
  threadId: string | null
  turns: SessionTurn[]
  itemsByTurn: Record<string, SessionItem[]>
}

/**
 * Target model for ComposerPane in session_v2.
 * Keep this shape aligned with `ComposerPane` props.
 */
export type BreadcrumbComposerModelOption = {
  value: string
  label: string
}

export type BreadcrumbComposerAdapterModel = {
  isTurnRunning: boolean
  disabled?: boolean
  onSubmit: (payload: ComposerSubmitPayload) => Promise<void>
  onInterrupt: () => Promise<void>
  currentCwd?: string | null
  modelOptions?: BreadcrumbComposerModelOption[]
  selectedModel?: string | null
  onModelChange?: (model: string) => void
  isModelLoading?: boolean
}

/**
 * Generic adapter ports.
 * Concrete implementations can be V3-backed first, then swap to native session_v2.
 */
export interface BreadcrumbTranscriptAdapter<TSource> {
  toTranscriptModel(
    source: TSource,
    context: BreadcrumbSessionAdapterContext,
  ): BreadcrumbTranscriptAdapterModel
}

export interface BreadcrumbComposerAdapter<TSource> {
  readonly capabilities: BreadcrumbSessionAdapterCapabilities
  toComposerModel(
    source: TSource,
    context: BreadcrumbSessionAdapterContext,
  ): BreadcrumbComposerAdapterModel
}

export interface BreadcrumbPendingRequestAdapter<TSource> {
  toPendingRequest(
    source: TSource,
    context: BreadcrumbSessionAdapterContext,
  ): PendingServerRequest | null
  toUserInputAnswers(
    request: PendingServerRequest,
    result: Record<string, unknown>,
  ): UserInputAnswer[]
}

/**
 * Combined UI adapter contract.
 * This is the boundary used by breadcrumb surfaces that want to render
 * session_v2 transcript/composer widgets without changing business workflow rules.
 */
export type BreadcrumbSessionUiAdapter<
  TTranscriptSource,
  TComposerSource,
  TPendingRequestSource,
> = {
  transcript: BreadcrumbTranscriptAdapter<TTranscriptSource>
  composer: BreadcrumbComposerAdapter<TComposerSource>
  pendingRequest: BreadcrumbPendingRequestAdapter<TPendingRequestSource>
}

/**
 * Phase-1 source contracts for current breadcrumb/thread V3 runtime.
 * These are intentionally minimal and UI-facing so we can keep business logic out of adapter code.
 */
export type BreadcrumbV3TranscriptSource = {
  snapshot: ThreadSnapshotV3 | null
  streamingTextLane?: Record<string, StreamingTextLaneEntry>
  lastCompletedAtMs?: number | null
}

export type BreadcrumbV3ComposerSource = {
  composerState: ThreadComposerState
  submitText: (text: string) => Promise<void>
  interruptTurn?: (() => Promise<void>) | null
  currentCwd?: string | null
  modelOptions?: BreadcrumbComposerModelOption[]
  selectedModel?: string | null
  onModelChange?: (model: string) => void
  isModelLoading?: boolean
  disabled?: boolean
}

export type BreadcrumbV3PendingRequestSource = {
  snapshot: ThreadSnapshotV3 | null
}
