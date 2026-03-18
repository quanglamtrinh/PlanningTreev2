import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAgentEventStream, usePlanningEventStream } from '../../api/hooks'
import type { SplitMode } from '../../api/types'
import { useProjectStore } from '../../stores/project-store'
import { useUIStore } from '../../stores/ui-store'
import { WorkspaceSetup } from '../auth/WorkspaceSetup'
import { Sidebar } from './Sidebar'
import { TreeGraph } from './TreeGraph'
import styles from './GraphWorkspace.module.css'

function buildComposerSeed(title: string, description: string) {
  return `Task: ${title}\nDescription: ${description}\n\nPlease help me complete this task.`
}

function resolveBreadcrumbTab(
  phase:
    | 'planning'
    | 'awaiting_brief'
    | 'spec_review'
    | 'ready_for_execution'
    | 'executing'
    | 'blocked_on_spec_question'
    | 'closed',
) {
  if (phase === 'awaiting_brief') {
    return 'briefing' as const
  }
  if (phase === 'spec_review' || phase === 'blocked_on_spec_question') {
    return 'spec' as const
  }
  if (phase === 'ready_for_execution' || phase === 'executing') {
    return 'execution' as const
  }
  return 'task' as const
}

function countStatuses(statuses: string[]) {
  return statuses.reduce<Record<string, number>>((counts, status) => {
    counts[status] = (counts[status] ?? 0) + 1
    return counts
  }, {})
}

export function GraphWorkspace() {
  const navigate = useNavigate()
  const [showWorkspaceEditor, setShowWorkspaceEditor] = useState(false)

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
  useAgentEventStream(activeProjectId, selectedNodeId)

  useEffect(() => {
    setActiveSurface('graph')
    void initialize()
  }, [initialize, setActiveSurface])

  useEffect(() => {
    if (!bootstrap?.workspace_configured) {
      setShowWorkspaceEditor(false)
    }
  }, [bootstrap?.workspace_configured])

  const selectedNode = useMemo(() => {
    if (!snapshot) {
      return null
    }
    const effectiveNodeId = selectedNodeId ?? snapshot.tree_state.root_node_id
    return snapshot.tree_state.node_registry.find((node) => node.node_id === effectiveNodeId) ?? null
  }, [selectedNodeId, snapshot])

  const statusCounts = useMemo(() => {
    if (!snapshot) {
      return {}
    }
    return countStatuses(
      snapshot.tree_state.node_registry
        .filter((node) => !node.is_superseded)
        .map((node) => node.status),
    )
  }, [snapshot])

  async function handleWorkspaceSubmit(path: string) {
    try {
      await setWorkspaceRoot(path)
      setShowWorkspaceEditor(false)
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
    if (!snapshot) {
      return
    }
    try {
      await handleSelectNode(nodeId, true)
      const latestSnapshot = useProjectStore.getState().snapshot ?? snapshot
      const targetNode =
        latestSnapshot.tree_state.node_registry.find((item) => item.node_id === nodeId) ?? null
      navigate(`/projects/${latestSnapshot.project.id}/nodes/${nodeId}/chat`, {
        state: targetNode ? { activeTab: resolveBreadcrumbTab(targetNode.phase) } : undefined,
      })
    } catch {
      return
    }
  }

  async function handleFinishTask(nodeId: string) {
    try {
      if (!snapshot) {
        return
      }

      const latestSnapshot = useProjectStore.getState().snapshot
      if (!latestSnapshot) {
        return
      }
      const targetNode =
        latestSnapshot.tree_state.node_registry.find((node) => node.node_id === nodeId) ?? null
      if (!targetNode) {
        return
      }

      await selectNode(nodeId, true)
      const activeTab = resolveBreadcrumbTab(targetNode.phase)
      navigate(`/projects/${latestSnapshot.project.id}/nodes/${nodeId}/chat`, {
        state:
          activeTab === 'execution'
            ? {
                activeTab,
                composerSeed: buildComposerSeed(targetNode.title, targetNode.description),
              }
            : { activeTab },
      })
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
      {/* ── Sidebar — left panel ── */}
      <Sidebar />

      {/* ── Main column: control rack + graph ── */}
      <div className={styles.mainColumn}>

        {/* ── Top control rack ── */}
        <div className={styles.controlRack}>

          {/* Section 1: Workspace */}
          <div className={styles.rackSection}>
            <span className={styles.sectionLabel}>WS</span>
            <button
              type="button"
              className={styles.rackBtn}
              onClick={() => setShowWorkspaceEditor((v) => !v)}
            >
              {showWorkspaceEditor ? 'Close' : 'Change Workspace'}
            </button>
            <span className={styles.workspacePath} title={baseWorkspaceRoot ?? ''}>
              {baseWorkspaceRoot}
            </span>
          </div>

          {/* Section 2: Actions — pushed to the right */}
          <div className={`${styles.rackSection} ${styles.rackSectionEnd}`}>
            <button
              type="button"
              className={`${styles.rackBtn} ${styles.rackBtnDanger}`}
              disabled={!activeProjectId || !snapshot || isLoadingSnapshot || isSplittingNode || isResettingProject}
              onClick={() => void handleResetProject()}
            >
              {isResettingProject ? 'Resetting…' : 'Reset to Root'}
            </button>
          </div>

        </div>

        {/* ── Inline workspace editor ── */}
        {showWorkspaceEditor ? (
          <div className={styles.workspaceEditor}>
            <WorkspaceSetup
              compact
              initialValue={baseWorkspaceRoot}
              isSaving={isWorkspaceSaving}
              error={error}
              onSubmit={handleWorkspaceSubmit}
              onCancel={() => setShowWorkspaceEditor(false)}
            />
          </div>
        ) : null}

        {/* ── Error banner ── */}
        {error ? <p className={styles.errorBanner}>{error}</p> : null}

        {/* ── Graph area: fills all remaining space ── */}
        <div className={styles.graphShell}>
          {/* Floating header overlay on top of graph */}
          <div className={styles.graphHeader}>
            <div className={styles.graphHeaderLeft}>
              <p className={styles.graphHeaderTitle}>
                {snapshot ? snapshot.project.name : 'No project loaded'}
              </p>
              {snapshot ? (
                <p className={styles.graphHeaderSub}>{snapshot.project.root_goal}</p>
              ) : null}
            </div>
            <div className={styles.graphHeaderChips}>
              {snapshot ? (
                <>
                  <span className={styles.chip}>
                    {snapshot.tree_state.node_registry.length} nodes
                  </span>
                  <span className={styles.chip}>{statusCounts.ready ?? 0} ready</span>
                  <span className={styles.chip}>{statusCounts.done ?? 0} done</span>
                  {selectedNode ? (
                    <span className={styles.chipAccent}>
                      {selectedNode.hierarchical_number} / {selectedNode.title}
                    </span>
                  ) : null}
                </>
              ) : null}
            </div>
          </div>

          {/* Graph or empty state */}
          {snapshot ? (
            <TreeGraph
              snapshot={snapshot}
              selectedNodeId={selectedNodeId}
              isCreatingNode={isCreatingNode}
              isSplittingNode={isSplittingNode}
              splittingNodeId={splittingNodeId}
              onSelectNode={handleSelectNode}
              onCreateChild={handleCreateChild}
              onSplitNode={handleSplitNode}
              onOpenBreadcrumb={handleOpenBreadcrumb}
              onFinishTask={handleFinishTask}
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
