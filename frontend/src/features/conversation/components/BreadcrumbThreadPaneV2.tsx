import type { ReactNode } from 'react'
import type { NodeRecord } from '../../../api/types'
import { ComposerBar } from '../../breadcrumb/ComposerBar'
import { FrameContextFeedBlock } from '../../breadcrumb/FrameContextFeedBlock'
import styles from '../../breadcrumb/BreadcrumbChatView.module.css'
import { type ThreadTab } from '../surfaceRouting'
import {
  type ThreadActionHandlers,
  type ThreadAskFollowupQueueActions,
  type ThreadAskFollowupQueueState,
  type ThreadComposerState,
  type ThreadExecutionFollowupQueueActions,
  type ThreadExecutionFollowupQueueState,
} from '../state/threadByIdStoreV3'
import { AskFollowupQueuePanelV2 } from './AskFollowupQueuePanelV2'
import { BreadcrumbThreadTabsV2 } from './BreadcrumbThreadTabsV2'
import { ExecutionFollowupQueuePanelV2 } from './ExecutionFollowupQueuePanelV2'
import { MessagesV3 } from './v3/MessagesV3'
import { MessagesV3ErrorBoundary } from './v3/MessagesV3ErrorBoundary'

export type BreadcrumbThreadConversationProps = {
  threadTab: ThreadTab
  onThreadTabChange: (threadTab: ThreadTab) => void
  combinedError: string | null
  showAuditShell: boolean
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
}

export type BreadcrumbThreadFrameContextProps = {
  projectId: string | undefined
  nodeId: string | undefined
  nodeRegistry: NodeRecord[] | null
  specConfirmed: boolean
}

export type BreadcrumbThreadExecutionQueueProps = {
  executionQueueState: ThreadExecutionFollowupQueueState
  executionQueueActions: Pick<
    ThreadExecutionFollowupQueueActions,
    'removeQueued' | 'reorderQueued' | 'sendQueuedNow' | 'confirmQueued' | 'retryQueued' | 'setOperatorPause'
  >
}

export type BreadcrumbThreadAskQueueProps = {
  askQueueState: ThreadAskFollowupQueueState
  askQueueActions: Pick<
    ThreadAskFollowupQueueActions,
    'removeQueued' | 'reorderAskQueued' | 'sendAskQueuedNow' | 'confirmQueued' | 'retryAskQueued'
  >
}

export type BreadcrumbThreadComposerProps = {
  composerWorkflowActions: ReactNode | null
  composerDisabled: boolean
  earlyResponsePhase: ThreadComposerState['earlyResponse']['phase']
  onSend: (content: string) => void
}

type BreadcrumbThreadPaneV2Props = {
  conversationProps: BreadcrumbThreadConversationProps
  frameContextProps: BreadcrumbThreadFrameContextProps
  executionQueueProps: BreadcrumbThreadExecutionQueueProps
  askQueueProps: BreadcrumbThreadAskQueueProps
  composerProps: BreadcrumbThreadComposerProps
}

export function BreadcrumbThreadPaneV2({
  conversationProps,
  frameContextProps,
  executionQueueProps,
  askQueueProps,
  composerProps,
}: BreadcrumbThreadPaneV2Props) {
  const {
    threadTab,
    onThreadTabChange,
    combinedError,
    showAuditShell,
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
  } = conversationProps
  const { projectId, nodeId, nodeRegistry, specConfirmed } = frameContextProps
  const { executionQueueState, executionQueueActions } = executionQueueProps
  const { askQueueState, askQueueActions } = askQueueProps
  const { composerWorkflowActions, composerDisabled, earlyResponsePhase, onSend } = composerProps

  return (
    <div className={styles.threadPane} data-testid="breadcrumb-thread-pane">
      <div className={styles.threadSurface}>
        <BreadcrumbThreadTabsV2
          threadTab={threadTab}
          onThreadTabChange={onThreadTabChange}
        />

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
              <ExecutionFollowupQueuePanelV2
                executionQueueState={executionQueueState}
                executionQueueActions={executionQueueActions}
              />
            ) : null}
            {threadTab === 'ask' && askQueueState.askFollowupQueueEnabled ? (
              <AskFollowupQueuePanelV2
                askQueueState={askQueueState}
                askQueueActions={askQueueActions}
              />
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
