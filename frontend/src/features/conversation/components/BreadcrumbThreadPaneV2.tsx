import type { ReactNode } from 'react'
import type { PendingServerRequest } from '../../session_v2/contracts'
import { ComposerPane } from '../../session_v2/components/ComposerPane'
import { RequestUserInputOverlay } from '../../session_v2/components/RequestUserInputOverlay'
import { TranscriptPanel } from '../../session_v2/components/TranscriptPanel'
import sessionShellStyles from '../../session_v2/shell/SessionConsoleV2.module.css'
import type { NodeRecord } from '../../../api/types'
import styles from '../../breadcrumb/BreadcrumbChatView.module.css'
import type {
  BreadcrumbComposerAdapterModel,
  BreadcrumbTranscriptAdapterModel,
} from '../sessionV2AdapterContracts'
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

export type BreadcrumbThreadTranscriptProps = BreadcrumbTranscriptAdapterModel
export type BreadcrumbThreadComposerProps = BreadcrumbComposerAdapterModel

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
      <div className={`${styles.threadPane} ${sessionShellStyles.themeScope}`} data-testid="breadcrumb-thread-pane">
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
                isExecutionTab ? ` ${styles.threadExecutionWhiteCanvas}` : ''
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
              className={`${styles.threadBodyComposer}${
                isExecutionTab ? ` ${styles.threadExecutionWhiteCanvas}` : ''
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

      {pendingRequestProps.request ? (
        <RequestUserInputOverlay
          request={pendingRequestProps.request}
          onResolve={pendingRequestProps.onResolve}
          onReject={pendingRequestProps.onReject}
        />
      ) : null}
    </>
  )
}
