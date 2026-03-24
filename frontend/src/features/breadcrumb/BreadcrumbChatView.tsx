import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useChatStore } from '../../stores/chat-store'
import { useProjectStore } from '../../stores/project-store'
import { NodeDetailCard } from '../node/NodeDetailCard'
import { ComposerBar } from './ComposerBar'
import { MessageFeed } from './MessageFeed'
import styles from './BreadcrumbChatView.module.css'

type ThreadTab = 'ask' | 'execution' | 'audit'

export function BreadcrumbChatView() {
  const { projectId, nodeId } = useParams<{ projectId: string; nodeId: string }>()
  const [threadTab, setThreadTab] = useState<ThreadTab>('ask')

  const { session, isLoading, isSending, error, loadSession, sendMessage, disconnect } = useChatStore(
    useShallow((s) => ({
      session: s.session,
      isLoading: s.isLoading,
      isSending: s.isSending,
      error: s.error,
      loadSession: s.loadSession,
      sendMessage: s.sendMessage,
      disconnect: s.disconnect,
    })),
  )

  const {
    activeProjectId,
    snapshot,
    selectedNodeId,
    isLoadingSnapshot,
    error: projectError,
    loadProject,
    selectNode,
  } = useProjectStore(
    useShallow((state) => ({
      activeProjectId: state.activeProjectId,
      snapshot: state.snapshot,
      selectedNodeId: state.selectedNodeId,
      isLoadingSnapshot: state.isLoadingSnapshot,
      error: state.error,
      loadProject: state.loadProject,
      selectNode: state.selectNode,
    })),
  )

  useEffect(() => {
    if (projectId && nodeId) {
      void loadSession(projectId, nodeId)
    }
    return () => {
      disconnect()
    }
  }, [projectId, nodeId, loadSession, disconnect])

  useEffect(() => {
    if (!projectId) {
      return
    }
    if (snapshot?.project.id === projectId) {
      return
    }
    if (isLoadingSnapshot && activeProjectId === projectId) {
      return
    }
    if (projectError && activeProjectId === projectId) {
      return
    }
    void loadProject(projectId).catch(() => undefined)
  }, [projectId, snapshot?.project.id, isLoadingSnapshot, activeProjectId, projectError, loadProject])

  const detailNode = useMemo(() => {
    if (!projectId || !nodeId || !snapshot || snapshot.project.id !== projectId) {
      return null
    }
    return snapshot.tree_state.node_registry.find((node) => node.node_id === nodeId) ?? null
  }, [projectId, nodeId, snapshot])

  useEffect(() => {
    if (!projectId || !nodeId || !detailNode || !snapshot || snapshot.project.id !== projectId) {
      return
    }
    if (selectedNodeId === nodeId) {
      return
    }
    void selectNode(nodeId, false).catch(() => undefined)
  }, [projectId, nodeId, detailNode, snapshot, selectedNodeId, selectNode])

  const detailState = useMemo(() => {
    if (!projectId || !nodeId) {
      return 'unavailable' as const
    }
    if (snapshot?.project.id === projectId && detailNode) {
      return 'ready' as const
    }
    if (isLoadingSnapshot && activeProjectId === projectId) {
      return 'loading' as const
    }
    if (!projectError && (!snapshot || snapshot.project.id !== projectId)) {
      return 'loading' as const
    }
    return 'unavailable' as const
  }, [projectId, nodeId, snapshot, detailNode, isLoadingSnapshot, activeProjectId, projectError])

  const detailMessage = useMemo(() => {
    if (!projectId || !nodeId) {
      return 'This breadcrumb route is missing its project or node id.'
    }
    if (detailState === 'loading') {
      return 'The node snapshot is loading for this breadcrumb route.'
    }
    if (projectError && activeProjectId === projectId) {
      return projectError
    }
    if (snapshot?.project.id === projectId && !detailNode) {
      return 'This node was not found in the current project snapshot.'
    }
    return 'Node details are unavailable for this breadcrumb route.'
  }, [projectId, nodeId, detailState, projectError, activeProjectId, snapshot, detailNode])

  const isActiveTurn = !!session?.active_turn_id
  const composerDisabledAsk = isActiveTurn || isSending || isLoading || !session

  return (
    <div className={styles.root}>
      <div className={styles.threadPane} data-testid="breadcrumb-thread-pane">
        <div className={styles.threadSurface}>
          <nav className={styles.threadTabBar} role="tablist" aria-label="Thread mode">
            <button
              type="button"
              role="tab"
              className={`${styles.threadTab} ${threadTab === 'ask' ? styles.threadTabActive : ''}`}
              data-testid="breadcrumb-thread-tab-ask"
              aria-selected={threadTab === 'ask'}
              onClick={() => setThreadTab('ask')}
            >
              Ask
            </button>
            <button
              type="button"
              role="tab"
              className={`${styles.threadTab} ${threadTab === 'execution' ? styles.threadTabActive : ''}`}
              data-testid="breadcrumb-thread-tab-execution"
              aria-selected={threadTab === 'execution'}
              onClick={() => setThreadTab('execution')}
            >
              Execution
            </button>
            <button
              type="button"
              role="tab"
              className={`${styles.threadTab} ${threadTab === 'audit' ? styles.threadTabActive : ''}`}
              data-testid="breadcrumb-thread-tab-audit"
              aria-selected={threadTab === 'audit'}
              onClick={() => setThreadTab('audit')}
            >
              Audit
            </button>
          </nav>

          <div className={styles.threadTabBody}>
            {threadTab === 'ask' ? (
              <>
                {isLoading && (
                  <div className={styles.loadingState}>
                    Loading...
                  </div>
                )}
                {error && (
                  <div className={styles.errorBanner}>
                    {error}
                  </div>
                )}
                {!isLoading && session && (
                  <MessageFeed messages={session.messages} />
                )}
                <ComposerBar
                  onSend={sendMessage}
                  disabled={composerDisabledAsk}
                />
              </>
            ) : (
              <>
                <MessageFeed messages={[]} />
                <ComposerBar onSend={sendMessage} disabled />
              </>
            )}
          </div>
        </div>
      </div>

      <aside className={styles.detailPane} data-testid="breadcrumb-detail-pane">
        <div className={styles.detailRail}>
          <NodeDetailCard
            projectId={projectId ?? null}
            node={detailNode}
            variant="breadcrumb"
            showClose={false}
            state={detailState}
            message={detailMessage}
          />
        </div>
      </aside>
    </div>
  )
}
