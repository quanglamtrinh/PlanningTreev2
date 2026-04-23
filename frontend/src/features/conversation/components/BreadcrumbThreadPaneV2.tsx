import type { ReactNode } from 'react'
import { ApprovalOverlay } from '../../session_v2/components/ApprovalOverlay'
import type { PendingServerRequest, SessionItem, SessionTurn } from '../../session_v2/contracts'
import { ComposerPane } from '../../session_v2/components/ComposerPane'
import { McpElicitationOverlay } from '../../session_v2/components/McpElicitationOverlay'
import { RequestUserInputOverlay } from '../../session_v2/components/RequestUserInputOverlay'
import { TranscriptPanel } from '../../session_v2/components/TranscriptPanel'
import sessionShellStyles from '../../session_v2/shell/SessionConsoleV2.module.css'
import type { NodeRecord } from '../../../api/types'
import type { ComposerSubmitPayload } from '../../session_v2/components/ComposerPane'
import { type ThreadTab } from '../surfaceRouting'
import { BreadcrumbThreadTabsV2 } from './BreadcrumbThreadTabsV2'
import { WorkflowActionStripV2 } from './WorkflowActionStripV2'

export type BreadcrumbThreadFrameContextProps = {
  threadTab: ThreadTab
  onThreadTabChange: (threadTab: ThreadTab) => void
  combinedError: string | null
  projectId: string | undefined
  nodeId: string | undefined
  nodeRegistry: NodeRecord[] | null
  specConfirmed: boolean
}

export type BreadcrumbThreadTranscriptProps = {
  threadId: string | null
  turns: SessionTurn[]
  itemsByTurn: Record<string, SessionItem[]>
}

export type BreadcrumbThreadComposerProps = {
  isTurnRunning: boolean
  disabled?: boolean
  onSubmit: (payload: ComposerSubmitPayload) => Promise<void>
  onInterrupt: () => Promise<void>
  currentCwd?: string | null
  modelOptions?: Array<{ value: string; label: string }>
  selectedModel?: string | null
  onModelChange?: (model: string) => void
  isModelLoading?: boolean
}

export type BreadcrumbThreadPendingRequestProps = {
  request: PendingServerRequest | null
  onResolve: (result: Record<string, unknown>) => Promise<void>
  onReject: (reason?: string | null) => Promise<void>
}

export type BreadcrumbThreadWorkflowStripProps = {
  actions: ReactNode | null
}

type BreadcrumbThreadPaneV2Props = {
  transcriptProps: BreadcrumbThreadTranscriptProps
  frameContextProps: BreadcrumbThreadFrameContextProps
  pendingRequestProps: BreadcrumbThreadPendingRequestProps
  workflowStripProps: BreadcrumbThreadWorkflowStripProps
  composerProps: BreadcrumbThreadComposerProps
}

export function BreadcrumbThreadPaneV2({
  transcriptProps,
  frameContextProps,
  pendingRequestProps,
  workflowStripProps,
  composerProps,
}: BreadcrumbThreadPaneV2Props) {
  const { threadTab, onThreadTabChange, combinedError } = frameContextProps
  const isExecutionTab = threadTab === 'execution'

  return (
    <>
      <div
        className={`${sessionShellStyles.threadPane} ${sessionShellStyles.themeScope}`}
        data-testid="breadcrumb-thread-pane"
      >
        <div className={sessionShellStyles.threadSurface}>
          <BreadcrumbThreadTabsV2
            threadTab={threadTab}
            onThreadTabChange={onThreadTabChange}
          />

          <div className={sessionShellStyles.threadTabBody} data-testid="breadcrumb-thread-body">
            <div className={sessionShellStyles.threadBodyNoticeRow}>
              {combinedError ? (
                <div className={sessionShellStyles.threadErrorBanner} role="alert">
                  {combinedError}
                </div>
              ) : null}
            </div>

            <div
              className={`${sessionShellStyles.threadBodyMain}${
                isExecutionTab ? ` ${sessionShellStyles.threadExecutionWhiteCanvas}` : ''
              }`}
            >
              <TranscriptPanel
                threadId={transcriptProps.threadId}
                turns={transcriptProps.turns}
                itemsByTurn={transcriptProps.itemsByTurn}
              />
            </div>

            <WorkflowActionStripV2 actions={workflowStripProps.actions} />

            <div
              className={`${sessionShellStyles.threadBodyComposer}${
                isExecutionTab ? ` ${sessionShellStyles.threadExecutionWhiteCanvas}` : ''
              }`}
              data-testid="breadcrumb-thread-composer"
            >
              <ComposerPane
                isTurnRunning={composerProps.isTurnRunning}
                disabled={composerProps.disabled}
                onSubmit={composerProps.onSubmit}
                onInterrupt={composerProps.onInterrupt}
                currentCwd={composerProps.currentCwd}
                modelOptions={composerProps.modelOptions}
                selectedModel={composerProps.selectedModel}
                onModelChange={composerProps.onModelChange}
                isModelLoading={composerProps.isModelLoading}
              />
            </div>
          </div>
        </div>
      </div>

      {pendingRequestProps.request?.method === 'item/tool/requestUserInput' ? (
        <RequestUserInputOverlay
          request={pendingRequestProps.request}
          onResolve={pendingRequestProps.onResolve}
          onReject={pendingRequestProps.onReject}
        />
      ) : null}

      {pendingRequestProps.request?.method === 'mcpServer/elicitation/request' ? (
        <McpElicitationOverlay
          request={pendingRequestProps.request}
          onResolve={pendingRequestProps.onResolve}
          onReject={pendingRequestProps.onReject}
        />
      ) : null}

      {pendingRequestProps.request &&
      pendingRequestProps.request.method !== 'item/tool/requestUserInput' &&
      pendingRequestProps.request.method !== 'mcpServer/elicitation/request' ? (
        <ApprovalOverlay
          request={pendingRequestProps.request}
          onResolve={pendingRequestProps.onResolve}
          onReject={pendingRequestProps.onReject}
        />
      ) : null}
    </>
  )
}
