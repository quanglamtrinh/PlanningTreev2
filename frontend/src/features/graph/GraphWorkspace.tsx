import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import type { SplitMode } from '../../api/types'
import { buildChatV2Url } from '../conversation/surfaceRouting'
import { useProjectStore } from '../../stores/project-store'
import { useUIStore } from '../../stores/ui-store'
import { Sidebar } from './Sidebar'
import { TreeGraph } from './TreeGraph'
import styles from './GraphWorkspace.module.css'

export function GraphWorkspace() {
  const navigate = useNavigate()

  const {
    initialize,
    resetProjectToRoot,
    selectNode,
    createChild,
    createTask,
    splitNode,
    hasInitialized,
    isInitializing,
    bootstrap,
    projects,
    activeProjectId,
    snapshot,
    selectedNodeId,
    splitStatus,
    splitNodeId,
    error,
    isLoadingSnapshot,
    isCreatingNode,
    isResettingProject,
  } = useProjectStore(
    useShallow((state) => ({
      initialize: state.initialize,
      resetProjectToRoot: state.resetProjectToRoot,
      selectNode: state.selectNode,
      createChild: state.createChild,
      createTask: state.createTask,
      splitNode: state.splitNode,
      hasInitialized: state.hasInitialized,
      isInitializing: state.isInitializing,
      bootstrap: state.bootstrap,
      projects: state.projects,
      activeProjectId: state.activeProjectId,
      snapshot: state.snapshot,
      selectedNodeId: state.selectedNodeId,
      splitStatus: state.splitStatus,
      splitNodeId: state.splitNodeId,
      error: state.error,
      isLoadingSnapshot: state.isLoadingSnapshot,
      isCreatingNode: state.isCreatingNode,
      isResettingProject: state.isResettingProject,
    })),
  )
  const setActiveSurface = useUIStore((state) => state.setActiveSurface)

  useEffect(() => {
    setActiveSurface('graph')
    void initialize()
  }, [initialize, setActiveSurface])

  // Dynamic window title
  useEffect(() => {
    const projectName = snapshot?.project?.name
    if (window.electronAPI?.setWindowTitle) {
      window.electronAPI.setWindowTitle(
        projectName ? `${projectName} \u2014 PlanningTree` : 'PlanningTree',
      )
    }
    return () => {
      window.electronAPI?.setWindowTitle?.('PlanningTree')
    }
  }, [snapshot?.project?.name])

  async function handleSelectNode(nodeId: string, persist = true) {
    try {
      await selectNode(nodeId, persist)
    } catch {
      return
    }
  }

  async function handleCreateChild(parentId: string) {
    try {
      await createChild(parentId)
    } catch {
      return
    }
  }

  async function handleCreateTask(parentId: string, description: string) {
    try {
      return await createTask(parentId, description)
    } catch {
      return null
    }
  }

  async function handleOpenBreadcrumb(nodeId: string) {
    const latestState = useProjectStore.getState()
    const latestSnapshot = latestState.snapshot
    const projectId = latestSnapshot?.project.id ?? latestState.activeProjectId
    if (!projectId) {
      return
    }

    if (
      latestSnapshot &&
      latestSnapshot.project.id === projectId &&
      !latestSnapshot.tree_state.node_registry.some((item) => item.node_id === nodeId)
      ) {
      return
    }

    const targetNode = latestSnapshot?.tree_state.node_registry.find((item) => item.node_id === nodeId)
    const destination =
      targetNode?.node_kind === 'review'
        ? buildChatV2Url(projectId, nodeId, 'audit')
        : buildChatV2Url(projectId, nodeId, 'ask')
    navigate(destination)
    void selectNode(nodeId, true)
  }

  async function handleSplitNode(nodeId: string, mode: SplitMode) {
    try {
      await splitNode(nodeId, mode)
    } catch {
      return
    }
  }

  async function handleResetProject() {
    const currentState = useProjectStore.getState()
    const currentSnapshot = currentState.snapshot
    if (!currentState.activeProjectId || !currentSnapshot) {
      return
    }

    const confirmed = window.confirm('Reset this project to its root node? This will delete all child nodes.')
    if (!confirmed) {
      return
    }

    try {
      await resetProjectToRoot()
    } catch {
      return
    }
  }

  if (!hasInitialized || isInitializing) {
    return <section className={styles.loading}>Loading...</section>
  }

  return (
    <section className={styles.view}>
      <Sidebar />

      <div className={styles.mainColumn}>
        {error ? <p className={styles.errorBanner}>{error}</p> : null}

        {bootstrap && !bootstrap.codex_available && (
          <div className={styles.codexBanner}>
            <strong>Codex CLI not found.</strong> AI features (Split, Chat) require the Codex
            CLI.{' '}
            <a href="https://github.com/openai/codex" target="_blank" rel="noreferrer">
              Install instructions
            </a>
          </div>
        )}

        <div className={styles.graphShell}>
          {snapshot ? (
            <TreeGraph
              snapshot={snapshot}
              selectedNodeId={selectedNodeId}
              splitStatus={splitStatus}
              splittingNodeId={splitNodeId}
              isCreatingNode={isCreatingNode}
              isResettingProject={isResettingProject}
              isResetDisabled={
                !activeProjectId || isLoadingSnapshot || isResettingProject || splitStatus === 'active'
              }
              codexAvailable={bootstrap?.codex_available ?? false}
              onSelectNode={handleSelectNode}
              onCreateChild={handleCreateChild}
              onCreateTask={handleCreateTask}
              onSplitNode={handleSplitNode}
              onOpenBreadcrumb={handleOpenBreadcrumb}
              onResetProject={handleResetProject}
            />
          ) : (
            <div className={styles.emptyState}>
              <h3>No project loaded</h3>
              <p>
                {isLoadingSnapshot
                  ? 'Loading snapshot...'
                  : projects.length > 0
                    ? 'Select a project from the sidebar to render its graph.'
                    : 'Add a project folder to get started.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
