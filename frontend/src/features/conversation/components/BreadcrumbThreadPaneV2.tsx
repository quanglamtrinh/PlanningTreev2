import type { ReactNode } from 'react'
import type { NodeRecord } from '../../../api/types'
import { ComposerBar } from '../../breadcrumb/ComposerBar'
import { FrameContextFeedBlock } from '../../breadcrumb/FrameContextFeedBlock'
import styles from '../../breadcrumb/BreadcrumbChatView.module.css'
import { type ThreadTab } from '../surfaceRouting'
import {
  type AskFollowupQueuePauseReason,
  type AskFollowupQueueStatus,
  type ExecutionFollowupQueuePauseReason,
  type ExecutionFollowupQueueStatus,
  type ThreadActionHandlers,
  type ThreadAskFollowupQueueActions,
  type ThreadAskFollowupQueueState,
  type ThreadComposerState,
  type ThreadExecutionFollowupQueueActions,
  type ThreadExecutionFollowupQueueState,
} from '../state/threadByIdStoreV3'
import { MessagesV3 } from './v3/MessagesV3'
import { MessagesV3ErrorBoundary } from './v3/MessagesV3ErrorBoundary'

type BreadcrumbThreadPaneV2Props = {
  threadTab: ThreadTab
  projectId: string | undefined
  nodeId: string | undefined
  onThreadTabChange: (threadTab: ThreadTab) => void
  combinedError: string | null
  showAuditShell: boolean
  nodeRegistry: NodeRecord[] | null
  specConfirmed: boolean
  activeThreadId: string | null
  feedSnapshot: ThreadComposerState['snapshot']
  conversationLoading: boolean
  isSending: boolean
  hasOlderHistory: boolean
  isLoadingHistory: boolean
  loadMoreHistory: ThreadActionHandlers['loadMoreHistory']
  resolveUserInput: ThreadActionHandlers['resolveUserInput']
  runPlanAction: ThreadActionHandlers['runPlanAction']
  lastCompletedAt: number | null
  lastDurationMs: number | null
  onRenderError: (error: Error) => void
  composerWorkflowActions: ReactNode | null
  composerDisabled: boolean
  earlyResponsePhase: ThreadComposerState['earlyResponse']['phase']
  onSend: (content: string) => void
  executionQueueState: ThreadExecutionFollowupQueueState
  askQueueState: ThreadAskFollowupQueueState
  executionQueueActions: Pick<
    ThreadExecutionFollowupQueueActions,
    'removeQueued' | 'reorderQueued' | 'sendQueuedNow' | 'confirmQueued' | 'retryQueued' | 'setOperatorPause'
  >
  askQueueActions: Pick<
    ThreadAskFollowupQueueActions,
    'removeQueued' | 'reorderAskQueued' | 'sendAskQueuedNow' | 'confirmQueued' | 'retryAskQueued'
  >
}

function renderQueueStatusLabel(status: ExecutionFollowupQueueStatus | AskFollowupQueueStatus): string {
  if (status === 'queued') {
    return 'Queued'
  }
  if (status === 'requires_confirmation') {
    return 'Needs confirmation'
  }
  if (status === 'sending') {
    return 'Sending'
  }
  return 'Failed'
}

function renderQueuePauseReasonLabel(reason: ExecutionFollowupQueuePauseReason): string {
  if (reason === 'none') {
    return 'Auto-send ready'
  }
  if (reason === 'runtime_waiting_input') {
    return 'Paused: waiting for required input'
  }
  if (reason === 'plan_ready_gate') {
    return 'Paused: plan-ready gate'
  }
  if (reason === 'operator_pause') {
    return 'Paused by operator'
  }
  return 'Paused: workflow blocked'
}

function renderAskQueuePauseReasonLabel(reason: AskFollowupQueuePauseReason): string {
  if (reason === 'none') {
    return 'Auto-send ready'
  }
  if (reason === 'snapshot_unavailable') {
    return 'Paused: snapshot unavailable'
  }
  if (reason === 'stream_or_state_mismatch') {
    return 'Paused: stream/state mismatch'
  }
  if (reason === 'active_turn_running') {
    return 'Paused: active turn running'
  }
  if (reason === 'waiting_user_input') {
    return 'Paused: waiting for required input'
  }
  if (reason === 'operator_pause') {
    return 'Paused by operator'
  }
  return 'Paused: confirmation required'
}

function renderAskConfirmationReasonLabel(reason: string | null | undefined): string {
  if (reason === 'stale_age') {
    return 'Queued ask is stale. Confirm before sending.'
  }
  if (reason === 'thread_drift') {
    return 'Thread context changed. Confirm before sending.'
  }
  if (reason === 'snapshot_drift') {
    return 'Snapshot context changed. Confirm before sending.'
  }
  if (reason === 'stale_marker') {
    return 'Stream context changed. Confirm before sending.'
  }
  return 'Queued ask requires confirmation before sending.'
}

export function BreadcrumbThreadPaneV2({
  threadTab,
  projectId,
  nodeId,
  onThreadTabChange,
  combinedError,
  showAuditShell,
  nodeRegistry,
  specConfirmed,
  activeThreadId,
  feedSnapshot,
  conversationLoading,
  isSending,
  hasOlderHistory,
  isLoadingHistory,
  loadMoreHistory,
  resolveUserInput,
  runPlanAction,
  lastCompletedAt,
  lastDurationMs,
  onRenderError,
  composerWorkflowActions,
  composerDisabled,
  earlyResponsePhase,
  onSend,
  executionQueueState,
  askQueueState,
  executionQueueActions,
  askQueueActions,
}: BreadcrumbThreadPaneV2Props) {
  const executionQueueEntries = executionQueueState.executionFollowupQueue
  const executionQueueHasSending = executionQueueEntries.some((entry) => entry.status === 'sending')
  const executionQueueControlsDisabled = executionQueueHasSending || executionQueueState.isSending
  const executionQueuePauseLabel = renderQueuePauseReasonLabel(executionQueueState.executionQueuePauseReason)
  const askQueueEntries = askQueueState.askFollowupQueue
  const askQueueHasSending = askQueueEntries.some((entry) => entry.status === 'sending')
  const askQueueControlsDisabled = askQueueHasSending || askQueueState.isSending
  const askQueuePauseLabel = renderAskQueuePauseReasonLabel(askQueueState.askQueuePauseReason)
  const {
    removeQueued: removeExecutionQueued,
    reorderQueued,
    sendQueuedNow,
    confirmQueued: confirmExecutionQueued,
    retryQueued,
    setOperatorPause,
  } = executionQueueActions
  const {
    removeQueued: removeAskQueued,
    reorderAskQueued,
    sendAskQueuedNow,
    confirmQueued: confirmAskQueued,
    retryAskQueued,
  } = askQueueActions

  return (
    <div className={styles.threadPane} data-testid="breadcrumb-thread-pane">
      <div className={styles.threadSurface}>
        <div className={styles.threadTabBar} data-testid="breadcrumb-v2-thread-header">
          <nav className={styles.threadTabNav} role="tablist" aria-label="Thread mode">
            <button
              type="button"
              role="tab"
              className={`${styles.threadTab} ${threadTab === 'ask' ? styles.threadTabActive : ''}`}
              data-testid="breadcrumb-thread-tab-ask"
              aria-selected={threadTab === 'ask'}
              onClick={() => onThreadTabChange('ask')}
            >
              Ask
            </button>
            <button
              type="button"
              role="tab"
              className={`${styles.threadTab} ${threadTab === 'execution' ? styles.threadTabActive : ''}`}
              data-testid="breadcrumb-thread-tab-execution"
              aria-selected={threadTab === 'execution'}
              onClick={() => onThreadTabChange('execution')}
            >
              Execution
            </button>
            <button
              type="button"
              role="tab"
              className={`${styles.threadTab} ${threadTab === 'audit' ? styles.threadTabActive : ''}`}
              data-testid="breadcrumb-thread-tab-audit"
              aria-selected={threadTab === 'audit'}
              onClick={() => onThreadTabChange('audit')}
            >
              Review
            </button>
          </nav>
        </div>

        <div className={styles.threadTabBody} data-testid="breadcrumb-thread-body">
          <div className={styles.threadBodyNoticeRow}>
            {combinedError ? (
              <div className={styles.errorBanner} role="alert">
                {combinedError}
              </div>
            ) : null}
          </div>

          <div
            className={`${styles.threadBodyMain}${
              threadTab === 'execution' ? ` ${styles.threadExecutionWhiteCanvas}` : ''
            }`}
          >
            {showAuditShell ? (
              <div className={styles.auditShell} data-testid="audit-shell">
                {nodeRegistry && projectId && nodeId ? (
                  <FrameContextFeedBlock
                    projectId={projectId}
                    nodeId={nodeId}
                    nodeRegistry={nodeRegistry}
                    variant="audit"
                    specConfirmed={specConfirmed}
                  />
                ) : null}
                <div className={styles.auditShellBody}>
                  <div className={styles.auditShellTitle}>Review Thread Not Started Yet</div>
                  <div className={styles.auditShellText}>
                    Start review from the execution tab once the current execution decision is ready.
                  </div>
                </div>
              </div>
            ) : (
              <MessagesV3ErrorBoundary key={`${threadTab}:${activeThreadId ?? 'none'}`} onRenderError={onRenderError}>
                <MessagesV3
                  snapshot={feedSnapshot}
                  isLoading={conversationLoading}
                  isSending={isSending}
                  hasOlderHistory={hasOlderHistory}
                  isLoadingHistory={isLoadingHistory}
                  onLoadMoreHistory={() => void loadMoreHistory()}
                  onResolveUserInput={resolveUserInput}
                  onPlanAction={runPlanAction}
                  lastCompletedAt={lastCompletedAt}
                  lastDurationMs={lastDurationMs}
                  threadChatFlatCanvas
                  prefix={
                    (threadTab === 'ask' || threadTab === 'audit') && nodeRegistry && projectId && nodeId ? (
                      <FrameContextFeedBlock
                        projectId={projectId}
                        nodeId={nodeId}
                        nodeRegistry={nodeRegistry}
                        variant={threadTab === 'audit' ? 'audit' : 'ask'}
                        specConfirmed={specConfirmed}
                      />
                    ) : undefined
                  }
                  suffix={composerWorkflowActions ?? undefined}
                />
              </MessagesV3ErrorBoundary>
            )}
          </div>

          <div
            className={`${styles.threadBodyComposer}${
              threadTab === 'execution' ? ` ${styles.threadExecutionWhiteCanvas}` : ''
            }`}
            data-testid="breadcrumb-thread-composer"
          >
            {threadTab === 'execution' ? (
              <section
                className={styles.executionQueuePanel}
                aria-label="Queued execution follow-ups"
                data-testid="execution-followup-queue-panel"
              >
                <div className={styles.executionQueueHeader}>
                  <div className={styles.executionQueueTitle}>Queued Follow-ups ({executionQueueEntries.length})</div>
                  <div className={styles.executionQueueHeaderControls}>
                    <span className={styles.executionQueuePauseReason}>{executionQueuePauseLabel}</span>
                    <button
                      type="button"
                      className={styles.executionQueuePauseToggle}
                      onClick={() => setOperatorPause(!executionQueueState.executionQueueOperatorPaused)}
                      data-testid="execution-followup-operator-pause-toggle"
                    >
                      {executionQueueState.executionQueueOperatorPaused ? 'Resume auto-send' : 'Pause auto-send'}
                    </button>
                  </div>
                </div>

                {executionQueueEntries.length === 0 ? (
                  <p className={styles.executionQueueEmpty}>No queued follow-ups.</p>
                ) : (
                  <ol className={styles.executionQueueList}>
                    {executionQueueEntries.map((entry, index) => (
                      <li key={entry.entryId} className={styles.executionQueueItem}>
                        <div className={styles.executionQueueItemMetaRow}>
                          <span
                            className={`${styles.executionQueueStatusBadge} ${
                              entry.status === 'failed'
                                ? styles.executionQueueStatusFailed
                                : entry.status === 'requires_confirmation'
                                  ? styles.executionQueueStatusConfirmation
                                  : entry.status === 'sending'
                                    ? styles.executionQueueStatusSending
                                    : styles.executionQueueStatusQueued
                            }`}
                          >
                            {renderQueueStatusLabel(entry.status)}
                          </span>
                          <span className={styles.executionQueueMetaText}>Attempt {entry.attemptCount + 1}</span>
                        </div>
                        <p className={styles.executionQueueText}>{entry.text}</p>
                        {entry.lastError ? (
                          <div className={styles.executionQueueError}>Last error: {entry.lastError}</div>
                        ) : null}
                        <div className={styles.executionQueueActions}>
                          <button
                            type="button"
                            className={styles.executionQueueAction}
                            disabled={executionQueueControlsDisabled || index === 0}
                            onClick={() => reorderQueued(index, index - 1)}
                          >
                            Move up
                          </button>
                          <button
                            type="button"
                            className={styles.executionQueueAction}
                            disabled={executionQueueControlsDisabled || index === executionQueueEntries.length - 1}
                            onClick={() => reorderQueued(index, index + 1)}
                          >
                            Move down
                          </button>
                          <button
                            type="button"
                            className={styles.executionQueueAction}
                            disabled={
                              executionQueueControlsDisabled ||
                              entry.status === 'sending' ||
                              entry.status === 'requires_confirmation'
                            }
                            onClick={() => void sendQueuedNow(entry.entryId)}
                          >
                            Send now
                          </button>
                          {entry.status === 'requires_confirmation' ? (
                            <button
                              type="button"
                              className={`${styles.executionQueueAction} ${styles.executionQueueActionPrimary}`}
                              disabled={executionQueueControlsDisabled}
                              onClick={() => void confirmExecutionQueued(entry.entryId)}
                            >
                              Confirm
                            </button>
                          ) : null}
                          {entry.status === 'failed' ? (
                            <button
                              type="button"
                              className={`${styles.executionQueueAction} ${styles.executionQueueActionPrimary}`}
                              disabled={executionQueueControlsDisabled}
                              onClick={() => void retryQueued(entry.entryId)}
                            >
                              Retry
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className={styles.executionQueueAction}
                            disabled={executionQueueControlsDisabled || entry.status === 'sending'}
                            onClick={() => removeExecutionQueued(entry.entryId)}
                          >
                            Remove
                          </button>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            ) : null}
            {threadTab === 'ask' && askQueueState.askFollowupQueueEnabled ? (
              <section
                className={styles.askQueuePanel}
                aria-label="Queued ask follow-ups"
                data-testid="ask-followup-queue-panel"
              >
                <div className={styles.askQueueHeader}>
                  <div className={styles.askQueueTitle}>Queued Ask Follow-ups ({askQueueEntries.length})</div>
                  <div className={styles.askQueueHeaderControls}>
                    <span className={styles.askQueuePauseReason}>{askQueuePauseLabel}</span>
                  </div>
                </div>

                {askQueueEntries.length === 0 ? (
                  <p className={styles.askQueueEmpty}>No queued ask follow-ups.</p>
                ) : (
                  <ol className={styles.askQueueList}>
                    {askQueueEntries.map((entry, index) => (
                      <li key={entry.entryId} className={styles.askQueueItem}>
                        <div className={styles.askQueueItemMetaRow}>
                          <span
                            className={`${styles.askQueueStatusBadge} ${
                              entry.status === 'failed'
                                ? styles.askQueueStatusFailed
                                : entry.status === 'requires_confirmation'
                                  ? styles.askQueueStatusConfirmation
                                  : entry.status === 'sending'
                                    ? styles.askQueueStatusSending
                                    : styles.askQueueStatusQueued
                            }`}
                          >
                            {renderQueueStatusLabel(entry.status)}
                          </span>
                          <span className={styles.askQueueMetaText}>Attempt {entry.attemptCount + 1}</span>
                        </div>
                        <p className={styles.askQueueText}>{entry.text}</p>
                        {entry.status === 'requires_confirmation' ? (
                          <div className={styles.askQueueReason}>
                            {renderAskConfirmationReasonLabel(entry.confirmationReason)}
                          </div>
                        ) : null}
                        {entry.lastError ? (
                          <div className={styles.askQueueError}>Last error: {entry.lastError}</div>
                        ) : null}
                        <div className={styles.askQueueActions}>
                          <button
                            type="button"
                            className={styles.askQueueAction}
                            disabled={askQueueControlsDisabled || index === 0}
                            onClick={() => reorderAskQueued(index, index - 1)}
                          >
                            Move up
                          </button>
                          <button
                            type="button"
                            className={styles.askQueueAction}
                            disabled={askQueueControlsDisabled || index === askQueueEntries.length - 1}
                            onClick={() => reorderAskQueued(index, index + 1)}
                          >
                            Move down
                          </button>
                          <button
                            type="button"
                            className={styles.askQueueAction}
                            disabled={askQueueControlsDisabled || index !== 0 || entry.status !== 'queued'}
                            onClick={() => void sendAskQueuedNow(entry.entryId)}
                          >
                            Send now
                          </button>
                          {entry.status === 'requires_confirmation' ? (
                            <button
                              type="button"
                              className={`${styles.askQueueAction} ${styles.askQueueActionPrimary}`}
                              disabled={askQueueControlsDisabled}
                              onClick={() => void confirmAskQueued(entry.entryId)}
                            >
                              Confirm
                            </button>
                          ) : null}
                          {entry.status === 'failed' ? (
                            <button
                              type="button"
                              className={`${styles.askQueueAction} ${styles.askQueueActionPrimary}`}
                              disabled={askQueueControlsDisabled}
                              onClick={() => void retryAskQueued(entry.entryId)}
                            >
                              Retry
                            </button>
                          ) : null}
                          <button
                            type="button"
                            className={styles.askQueueAction}
                            disabled={askQueueControlsDisabled || entry.status === 'sending'}
                            onClick={() => removeAskQueued(entry.entryId)}
                          >
                            Remove
                          </button>
                        </div>
                      </li>
                    ))}
                  </ol>
                )}
              </section>
            ) : null}
            <ComposerBar
              onSend={(content) => {
                onSend(content)
              }}
              disabled={composerDisabled}
              earlyResponsePhase={earlyResponsePhase}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
