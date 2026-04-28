import { ApprovalOverlay } from '../components/ApprovalOverlay'
import { ComposerPane } from '../components/ComposerPane'
import { McpElicitationOverlay } from '../components/McpElicitationOverlay'
import { RequestUserInputOverlay } from '../components/RequestUserInputOverlay'
import { ThreadListPanel } from '../components/ThreadListPanel'
import { TranscriptPanel } from '../components/TranscriptPanel'
import { useSessionFacadeV2 } from '../facade/useSessionFacadeV2'
import styles from './SessionConsoleV2.module.css'

export function SessionConsoleV2() {
  const { state, commands } = useSessionFacadeV2()
  const showBootstrapBanner = state.isBootstrapping && !state.activeThreadId && state.threads.length === 0

  return (
    <section className={styles.console}>
      <ThreadListPanel
        threads={state.threads}
        activeThreadId={state.activeThreadId}
        onCreateThread={() => {
          void commands.createThread()
        }}
        onRefresh={() => {
          void commands.refreshThreads()
        }}
        onSelectThread={(threadId) => {
          void commands.selectThread(threadId)
        }}
        onResumeThread={(threadId) => {
          void commands.selectThread(threadId)
        }}
        onForkThread={(threadId) => {
          void commands.forkThread(threadId)
        }}
      />

      <main className={styles.mainPane}>
        <header className={styles.statusBar}>
          <div>
            <strong>Session</strong>
            <span className={styles.muted}>connection: {state.connection.phase}</span>
          </div>
          <div className={styles.statusMeta}>
            <span>thread: {state.activeThread?.name ?? state.activeThreadId ?? 'none'}</span>
            <span>running: {state.activeRunningTurn ? 'yes' : 'no'}</span>
            <span>queue: {state.queueLength}</span>
            <span>gap: {state.activeThreadId ? (state.gapDetected ? 'yes' : 'no') : 'n/a'}</span>
          </div>
        </header>

        {showBootstrapBanner ? <div className={styles.banner}>Bootstrapping Session V2...</div> : null}
        {state.runtimeError ? <div className={styles.errorBanner}>{state.runtimeError}</div> : null}

        <TranscriptPanel
          threadId={state.activeThreadId}
          turns={state.activeTurns}
          itemsByTurn={state.activeItemsByTurn}
          visibleRows={state.activeVisibleTranscriptRows}
        />

        <ComposerPane
          isTurnRunning={Boolean(state.activeRunningTurn)}
          disabled={!state.activeThreadId || state.connection.phase === 'error'}
          onSubmit={commands.submit}
          onInterrupt={commands.interrupt}
          currentCwd={state.activeThread?.cwd ?? null}
          modelOptions={state.modelOptions}
          selectedModel={state.selectedModel}
          onModelChange={commands.setModel}
          isModelLoading={state.isModelLoading}
        />
      </main>

      {state.activeRequest?.method === 'item/tool/requestUserInput' ? (
        <RequestUserInputOverlay request={state.activeRequest} onResolve={commands.resolveRequest} onReject={commands.rejectRequest} />
      ) : null}

      {state.activeRequest?.method === 'mcpServer/elicitation/request' ? (
        <McpElicitationOverlay request={state.activeRequest} onResolve={commands.resolveRequest} onReject={commands.rejectRequest} />
      ) : null}

      {state.activeRequest &&
      state.activeRequest.method !== 'item/tool/requestUserInput' &&
      state.activeRequest.method !== 'mcpServer/elicitation/request' ? (
        <ApprovalOverlay request={state.activeRequest} onResolve={commands.resolveRequest} onReject={commands.rejectRequest} />
      ) : null}
    </section>
  )
}
