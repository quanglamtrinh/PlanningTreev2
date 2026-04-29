import type { ReactNode } from 'react'
import { ApprovalOverlay } from '../../session_v2/components/ApprovalOverlay'
import type { PendingServerRequest, SessionItem, SessionTurn, VisibleTranscriptRow } from '../../session_v2/contracts'
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
  showThreadTabs?: boolean
}

export type BreadcrumbThreadTranscriptProps = {
  threadId: string | null
  turns: SessionTurn[]
  itemsByTurn: Record<string, SessionItem[]>
  visibleRows: VisibleTranscriptRow[]
  workflowContextItem?: SessionItem | null
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
  onResolve: (requestId: string, result: Record<string, unknown>) => Promise<void>
  onReject: (requestId: string, reason?: string | null) => Promise<void>
}

export type BreadcrumbThreadWorkflowStripProps = {
  actions: ReactNode | null
}

export type BreadcrumbThreadDebugPanelProps = {
  enabled: boolean
  payload: Record<string, unknown> | null
  showWorkflowContextItems: boolean
  onToggleShowWorkflowContextItems: () => void
}

export type BreadcrumbThreadPaneV2Props = {
  transcriptProps: BreadcrumbThreadTranscriptProps
  frameContextProps: BreadcrumbThreadFrameContextProps
  pendingRequestProps: BreadcrumbThreadPendingRequestProps
  workflowStripProps: BreadcrumbThreadWorkflowStripProps
  composerProps: BreadcrumbThreadComposerProps
  debugPanelProps?: BreadcrumbThreadDebugPanelProps
}

export function BreadcrumbThreadPaneV2({
  transcriptProps,
  frameContextProps,
  pendingRequestProps,
  workflowStripProps,
  composerProps,
  debugPanelProps,
}: BreadcrumbThreadPaneV2Props) {
  const { threadTab, onThreadTabChange, combinedError, showThreadTabs = true } = frameContextProps
  const isExecutionTab = threadTab === 'execution'
  const debugPayloadText = debugPanelProps?.payload
    ? JSON.stringify(debugPanelProps.payload, null, 2)
    : ''

  return (
    <>
      <div
        className={`${sessionShellStyles.threadPane} ${sessionShellStyles.themeScope}`}
        data-testid="breadcrumb-thread-pane"
      >
        <div className={sessionShellStyles.threadSurface}>
          {showThreadTabs ? (
            <BreadcrumbThreadTabsV2
              threadTab={threadTab}
              onThreadTabChange={onThreadTabChange}
            />
          ) : null}

          <div className={sessionShellStyles.threadTabBody} data-testid="breadcrumb-thread-body">
            <div className={sessionShellStyles.threadBodyNoticeRow}>
              {combinedError ? (
                <div className={sessionShellStyles.threadErrorBanner} role="alert">
                  {combinedError}
                </div>
              ) : null}
              {debugPanelProps?.enabled ? (
                <section className={sessionShellStyles.threadDebugPanel} data-testid="session-debug-panel">
                  <div className={sessionShellStyles.threadDebugPanelHeader}>
                    <strong>Session Debug</strong>
                    <div className={sessionShellStyles.threadDebugPanelActions}>
                      <button
                        type="button"
                        className={sessionShellStyles.threadDebugButton}
                        onClick={() => {
                          if (!debugPayloadText) {
                            return
                          }
                          if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
                            void navigator.clipboard.writeText(debugPayloadText)
                            return
                          }
                          if (typeof document === 'undefined') {
                            return
                          }
                          const textarea = document.createElement('textarea')
                          textarea.value = debugPayloadText
                          textarea.setAttribute('readonly', 'true')
                          textarea.style.position = 'fixed'
                          textarea.style.left = '-9999px'
                          document.body.appendChild(textarea)
                          textarea.select()
                          try {
                            document.execCommand('copy')
                          } finally {
                            document.body.removeChild(textarea)
                          }
                        }}
                      >
                        Copy trace payload
                      </button>
                      <button
                        type="button"
                        className={sessionShellStyles.threadDebugButton}
                        onClick={debugPanelProps.onToggleShowWorkflowContextItems}
                      >
                        {debugPanelProps.showWorkflowContextItems ? 'Hide context items' : 'Show context items'}
                      </button>
                    </div>
                  </div>
                  <pre className={sessionShellStyles.threadDebugPanelBody}>{debugPayloadText || '{}'}</pre>
                </section>
              ) : null}
            </div>

            <div
              className={`${sessionShellStyles.threadBodyMain}${
                isExecutionTab ? ` ${sessionShellStyles.threadWhiteCanvas}` : ''
              }`}
            >
              <TranscriptPanel
                threadId={transcriptProps.threadId}
                turns={transcriptProps.turns}
                itemsByTurn={transcriptProps.itemsByTurn}
                visibleRows={transcriptProps.visibleRows}
                showWorkflowContext={false}
              />
            </div>

            <WorkflowActionStripV2 actions={workflowStripProps.actions} />

            <div
              className={`${sessionShellStyles.threadBodyComposer}${
                isExecutionTab ? ` ${sessionShellStyles.threadWhiteCanvas}` : ''
              }`}
              data-testid="breadcrumb-thread-composer"
            >
              {pendingRequestProps.request &&
              pendingRequestProps.request.method !== 'item/tool/requestUserInput' &&
              pendingRequestProps.request.method !== 'mcpServer/elicitation/request' ? (
                <ApprovalOverlay
                  request={pendingRequestProps.request}
                  onResolve={pendingRequestProps.onResolve}
                  onReject={pendingRequestProps.onReject}
                  variant="inline"
                />
              ) : null}
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
    </>
  )
}
