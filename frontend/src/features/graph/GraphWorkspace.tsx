import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { usePlanningEventStream } from '../../api/hooks'
import type { SplitMode } from '../../api/types'
import { useProjectStore } from '../../stores/project-store'
import { useUIStore } from '../../stores/ui-store'
import { WorkspaceSetup } from '../auth/WorkspaceSetup'
import { Sidebar } from './Sidebar'
import { TreeGraph } from './TreeGraph'
import styles from './GraphWorkspace.module.css'

export function GraphWorkspace() {
  const navigate = useNavigate()

  const initialize = useProjectStore((state) => state.initialize)
  const setWorkspaceRoot = useProjectStore((state) => state.setWorkspaceRoot)
  const resetProjectToRoot = useProjectStore((state) => state.resetProjectToRoot)
  const selectNode = useProjectStore((state) => state.selectNode)
  const createChild = useProjectStore((state) => state.createChild)
  const splitNode = useProjectStore((state) => state.splitNode)
  const hasInitialized = useProjectStore((state) => state.hasInitialized)
  const isInitializing = useProjectStore((state) => state.isInitializing)
  const bootstrap = useProjectStore((state) => state.bootstrap)
  const baseWorkspaceRoot = useProjectStore((state) => state.baseWorkspaceRoot)
  const projects = useProjectStore((state) => state.projects)
  const activeProjectId = useProjectStore((state) => state.activeProjectId)
  const snapshot = useProjectStore((state) => state.snapshot)
  const selectedNodeId = useProjectStore((state) => state.selectedNodeId)
  const error = useProjectStore((state) => state.error)
  const isWorkspaceSaving = useProjectStore((state) => state.isWorkspaceSaving)
  const isLoadingSnapshot = useProjectStore((state) => state.isLoadingSnapshot)
  const isCreatingNode = useProjectStore((state) => state.isCreatingNode)
  const isSplittingNode = useProjectStore((state) => state.isSplittingNode)
  const isResettingProject = useProjectStore((state) => state.isResettingProject)
  const splittingNodeId = useProjectStore((state) => state.splittingNodeId)
  const setActiveSurface = useUIStore((state) => state.setActiveSurface)

  usePlanningEventStream(activeProjectId, splittingNodeId ?? selectedNodeId)

  useEffect(() => {
    setActiveSurface('graph')
    void initialize()
  }, [initialize, setActiveSurface])

  async function handleWorkspaceSubmit(path: string) {
    try {
      await setWorkspaceRoot(path)
    } catch {
      return
    }
  }

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

  async function handleSplitNode(nodeId: string, mode: SplitMode) {
    try {
      const latestSnapshot = useProjectStore.getState().snapshot
      if (!latestSnapshot) {
        return
      }

      const targetNode =
        latestSnapshot.tree_state.node_registry.find((node) => node.node_id === nodeId) ?? null
      if (!targetNode) {
        return
      }

      const activeChildren = targetNode.child_ids
        .map((childId) =>
          latestSnapshot.tree_state.node_registry.find((node) => node.node_id === childId) ?? null,
        )
        .filter((child) => Boolean(child && !child.is_superseded))

      let confirmReplace = false
      if (activeChildren.length > 0) {
        confirmReplace = window.confirm(
          "This will replace the node's current active children. Continue?",
        )
        if (!confirmReplace) {
          return
        }
      }

      await splitNode(nodeId, mode, confirmReplace)
    } catch {
      return
    }
  }

  async function handleOpenBreadcrumb(nodeId: string) {
    try {
      await selectNode(nodeId, true)
      const latestState = useProjectStore.getState()
      const latestSnapshot = latestState.snapshot
      if (!latestSnapshot || latestState.activeProjectId !== latestSnapshot.project.id) {
        return
      }
      const targetNode =
        latestSnapshot.tree_state.node_registry.find((item) => item.node_id === nodeId) ?? null
      if (!targetNode) {
        return
      }
      navigate(`/projects/${latestSnapshot.project.id}/nodes/${nodeId}/chat`)
    } catch {
      return
    }
  }

  async function handleFinishTask(nodeId: string) {
    try {
      await selectNode(nodeId, true)
      const latestState = useProjectStore.getState()
      const latestSnapshot = latestState.snapshot
      if (!latestSnapshot || latestState.activeProjectId !== latestSnapshot.project.id) {
        return
      }
      const targetNode =
        latestSnapshot.tree_state.node_registry.find((node) => node.node_id === nodeId) ?? null
      if (!targetNode) {
        return
      }
      navigate(`/projects/${latestSnapshot.project.id}/nodes/${nodeId}/chat`)
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

    const confirmed = window.confirm(
      'Reset this project to its root node? This will delete all child nodes and clear planning/chat history.',
    )
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
    return <section className={styles.loading}>Loading…</section>
  }

  if (!bootstrap?.workspace_configured) {
    return (
      <WorkspaceSetup
        initialValue={baseWorkspaceRoot}
        isSaving={isWorkspaceSaving}
        error={error}
        onSubmit={handleWorkspaceSubmit}
      />
    )
  }

  return (
    <section className={styles.view}>
      <Sidebar />

      <div className={styles.mainColumn}>
        {error ? <p className={styles.errorBanner}>{error}</p> : null}

        <div className={styles.graphShell}>
          {snapshot ? (
            <TreeGraph
              snapshot={snapshot}
              selectedNodeId={selectedNodeId}
              isCreatingNode={isCreatingNode}
              isSplittingNode={isSplittingNode}
              isResettingProject={isResettingProject}
              isResetDisabled={
                !activeProjectId || isLoadingSnapshot || isSplittingNode || isResettingProject
              }
              splittingNodeId={splittingNodeId}
              onSelectNode={handleSelectNode}
              onCreateChild={handleCreateChild}
              onSplitNode={handleSplitNode}
              onOpenBreadcrumb={handleOpenBreadcrumb}
              onFinishTask={handleFinishTask}
              onResetProject={handleResetProject}
            />
          ) : (
            <div className={styles.emptyState}>
              <h3>No project loaded</h3>
              <p>
                {isLoadingSnapshot
                  ? 'Loading snapshot…'
                  : projects.length > 0
                    ? 'Select a project from the sidebar to render its graph.'
                    : 'Create a project in the sidebar to get started.'}
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
