import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { NodeRecord, ProjectSummary, Snapshot } from '../../api/types'
import { useProjectStore } from '../../stores/project-store'
import styles from './Sidebar.module.css'

// ─── Relative time ────────────────────────────────────────────────────────────

function formatRelTime(isoString: string | null | undefined): string {
  if (!isoString) return ''
  const diffMs = Date.now() - new Date(isoString).getTime()
  const diffSec = Math.floor(diffMs / 1000)
  if (diffSec < 60) return `${diffSec}s`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay < 7) return `${diffDay}d`
  return `${Math.floor(diffDay / 7)}w`
}

// ─── Status dot ───────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const cls = status.replace(/[^a-z]/g, '')
  return <span className={`${styles.dot} ${styles[`dot_${cls}` as keyof typeof styles]}`} />
}

// ─── Constants ────────────────────────────────────────────────────────────────

const NODES_PER_PROJECT = 4

// ─── Sidebar ──────────────────────────────────────────────────────────────────

export function Sidebar() {
  const navigate = useNavigate()
  const [isCollapsed, setIsCollapsed] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set())
  const [isPickerLoading, setIsPickerLoading] = useState(false)
  const [pickerError, setPickerError] = useState<string | null>(null)

  const projects = useProjectStore((s) => s.projects)
  const activeProjectId = useProjectStore((s) => s.activeProjectId)
  const isLoadingProjects = useProjectStore((s) => s.isLoadingProjects)
  const snapshot = useProjectStore((s) => s.snapshot)
  const selectedNodeId = useProjectStore((s) => s.selectedNodeId)

  const loadProject = useProjectStore((s) => s.loadProject)
  const refreshProjects = useProjectStore((s) => s.refreshProjects)
  const selectNode = useProjectStore((s) => s.selectNode)
  const createProject = useProjectStore((s) => s.createProject)
  const deleteProject = useProjectStore((s) => s.deleteProject)
  const setWorkspaceRoot = useProjectStore((s) => s.setWorkspaceRoot)

  const handleProjectClick = useCallback(
    (projectId: string) => { void loadProject(projectId) },
    [loadProject],
  )

  const handleNodeClick = useCallback(
    (nodeId: string) => { void selectNode(nodeId, true) },
    [selectNode],
  )

  const handleOpenBreadcrumb = useCallback(
    async (nodeId: string) => {
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
        navigate(`/projects/${latestSnapshot.project.id}/nodes/${targetNode.node_id}/chat`)
      } catch { /* ignore */ }
    },
    [navigate, selectNode],
  )

  // ── New project: open native OS folder picker → auto-create project ──────────
  const handleNewProjectClick = useCallback(async () => {
    setPickerError(null)
    setIsPickerLoading(true)
    try {
      // Opens native OS "Select Folder" dialog (same UX as VSCode "Add Workspace Folder")
      // @ts-expect-error — showDirectoryPicker not in all TS lib versions
      const handle = await window.showDirectoryPicker({ mode: 'readwrite' }) as { name: string }
      const folderName = handle.name

      // Ensure workspace root is configured; if not, set it to the picked folder name.
      // (Browser security prevents exposing full path; backend may need adjustment.)
      const state = useProjectStore.getState()
      if (!state.baseWorkspaceRoot) {
        try { await setWorkspaceRoot(folderName) } catch { /* will show error from createProject */ }
      }

      // Auto-create project using folder name — no form needed
      await createProject(folderName, folderName)
    } catch (e) {
      if (e instanceof Error && e.name !== 'AbortError') {
        setPickerError(e.message)
      }
      // AbortError = user cancelled picker — silently ignore
    } finally {
      setIsPickerLoading(false)
    }
  }, [createProject, setWorkspaceRoot])

  const handleRemoveProject = useCallback(
    async (projectId: string, projectName: string) => {
      if (!window.confirm(`Remove "${projectName}" from workspace?\nThis cannot be undone.`)) return
      try {
        await deleteProject(projectId)
      } catch (e) {
        if (e instanceof Error) setPickerError(e.message)
      }
    },
    [deleteProject],
  )

  const toggleExpand = useCallback((projectId: string) => {
    setExpandedProjects((prev) => {
      const next = new Set(prev)
      if (next.has(projectId)) { next.delete(projectId) } else { next.add(projectId) }
      return next
    })
  }, [])

  const toggleSidebar = useCallback(() => {
    setIsCollapsed((prev) => !prev)
  }, [])

  const visibleNodes = useMemo(() => getVisibleNodes(snapshot), [snapshot])

  if (isCollapsed) {
    return (
      <aside className={`${styles.sidebar} ${styles.sidebarCollapsed}`}>
        <button
          type="button"
          className={styles.collapsedToggle}
          onClick={toggleSidebar}
          aria-label="Expand projects sidebar"
          title="Expand projects sidebar"
        >
          <span className={styles.collapsedLabel}>Projects</span>
        </button>
      </aside>
    )
  }

  return (
    <aside className={styles.sidebar}>
      {/* ── Header ── */}
      <div className={styles.header}>
        <button
          type="button"
          className={styles.headerBtn}
          title="Collapse projects sidebar"
          aria-label="Collapse projects sidebar"
          onClick={toggleSidebar}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="m15 18-6-6 6-6" />
          </svg>
        </button>
        <span className={styles.headerTitle}>Projects</span>
        <div className={styles.headerActions}>
          {/* New project — opens native OS folder picker */}
          <button
            type="button"
            className={styles.headerBtn}
            title="Add project folder"
            aria-label="Add project folder"
            disabled={isPickerLoading}
            onClick={() => void handleNewProjectClick()}
          >
            {isPickerLoading ? (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className={styles.spinIcon}>
                <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
                <line x1="12" y1="11" x2="12" y2="17" />
                <line x1="9" y1="14" x2="15" y2="14" />
              </svg>
            )}
          </button>

          {/* Refresh */}
          <button
            type="button"
            className={styles.headerBtn}
            title="Refresh"
            onClick={() => void refreshProjects()}
            disabled={isLoadingProjects}
            aria-label="Refresh projects"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="23 4 23 10 17 10" />
              <polyline points="1 20 1 14 7 14" />
              <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
            </svg>
          </button>

          {/* Search */}
          <button
            type="button"
            className={`${styles.headerBtn} ${searchOpen ? styles.headerBtnActive : ''}`}
            title="Search"
            onClick={() => setSearchOpen((v) => !v)}
            aria-label="Toggle search"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </button>
        </div>
      </div>

      {/* Folder picker error */}
      {pickerError && <p className={styles.pickerError}>{pickerError}</p>}

      {/* ── Project list ── */}
      <div className={styles.body}>
        {projects.length === 0 && !isLoadingProjects ? (
          <div className={styles.emptyState}>
            <p>No projects yet.</p>
            <button
              type="button"
              className={styles.emptyNewBtn}
              disabled={isPickerLoading}
              onClick={() => void handleNewProjectClick()}
            >
              + Add project folder
            </button>
          </div>
        ) : (
          projects.map((project) => {
            const isActive = project.id === activeProjectId
            const projectNodes = isActive ? visibleNodes : []
            const isExpanded = expandedProjects.has(project.id)
            const displayedNodes = isExpanded ? projectNodes : projectNodes.slice(0, NODES_PER_PROJECT)
            const hasMore = projectNodes.length > NODES_PER_PROJECT && !isExpanded

            return (
              <ProjectGroup
                key={project.id}
                project={project}
                isActive={isActive}
                nodes={displayedNodes}
                selectedNodeId={selectedNodeId}
                hasMore={hasMore}
                onClickProject={handleProjectClick}
                onClickNode={handleNodeClick}
                onDoubleClickNode={handleOpenBreadcrumb}
                onClickMore={() => toggleExpand(project.id)}
                onRemoveProject={handleRemoveProject}
              />
            )
          })
        )}
      </div>

      {/* ── Footer ── */}
      <div className={styles.footer}>
        <div className={styles.usageBlock}>
          <div className={styles.usageRow}>
            <span className={styles.usageLabel}>Session</span>
            <span className={styles.usageHint}>· Resets 2 hours</span>
            <span className={styles.usagePct}>8%</span>
          </div>
          <div className={styles.usageBar}>
            <div className={styles.usageBarFill} style={{ width: '8%' }} />
          </div>
          <div className={styles.usageRow} style={{ marginTop: 8 }}>
            <span className={styles.usageLabel}>Weekly</span>
            <span className={styles.usageHint}>· Resets 6 days</span>
            <span className={styles.usagePct}>22%</span>
          </div>
          <div className={styles.usageBar}>
            <div className={styles.usageBarFillWeekly} style={{ width: '22%' }} />
          </div>
        </div>
        <div className={styles.footerActions}>
          <button type="button" className={styles.footerBtn} title="Account" aria-label="Account">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </button>
          <button type="button" className={styles.footerBtn} title="Settings" aria-label="Settings">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="3" />
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
            </svg>
          </button>
        </div>
      </div>
    </aside>
  )
}

// ─── ProjectGroup ─────────────────────────────────────────────────────────────

type ProjectGroupProps = {
  project: ProjectSummary
  isActive: boolean
  nodes: NodeRecord[]
  selectedNodeId: string | null
  hasMore: boolean
  onClickProject: (id: string) => void
  onClickNode: (id: string) => void
  onDoubleClickNode: (id: string) => Promise<void>
  onClickMore: () => void
  onRemoveProject: (id: string, name: string) => Promise<void>
}

function ProjectGroup({
  project, isActive, nodes, selectedNodeId, hasMore,
  onClickProject, onClickNode, onDoubleClickNode, onClickMore, onRemoveProject,
}: ProjectGroupProps) {
  return (
    <div className={`${styles.projectGroup} ${isActive ? styles.projectGroupActive : ''}`}>
      <div className={styles.projectHeaderRow}>
        <button
          type="button"
          className={styles.projectHeader}
          onClick={() => onClickProject(project.id)}
        >
          {project.name}
        </button>
        <button
          type="button"
          className={styles.removeBtn}
          title="Remove from workspace"
          aria-label={`Remove ${project.name} from workspace`}
          onClick={() => void onRemoveProject(project.id, project.name)}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="3 6 5 6 21 6" />
            <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
            <path d="M10 11v6M14 11v6" />
            <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
          </svg>
        </button>
      </div>

      {isActive && nodes.length > 0 && (
        <div className={styles.nodeList}>
          {nodes.map((node) => (
            <NodeRow
              key={node.node_id}
              node={node}
              isSelected={node.node_id === selectedNodeId}
              onClick={onClickNode}
              onDoubleClick={onDoubleClickNode}
            />
          ))}
          {hasMore && (
            <button type="button" className={styles.moreBtn} onClick={onClickMore}>
              More…
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ─── NodeRow ──────────────────────────────────────────────────────────────────

type NodeRowProps = {
  node: NodeRecord
  isSelected: boolean
  onClick: (id: string) => void
  onDoubleClick: (id: string) => Promise<void>
}

function NodeRow({ node, isSelected, onClick, onDoubleClick }: NodeRowProps) {
  return (
    <button
      type="button"
      className={`${styles.nodeRow} ${isSelected ? styles.nodeRowActive : ''}`}
      onClick={() => onClick(node.node_id)}
      onDoubleClick={() => void onDoubleClick(node.node_id)}
      title={`${node.title}\nDouble-click to open chat`}
    >
      <StatusDot status={node.status} />
      <span className={styles.nodeTitle}>{node.title}</span>
      {node.created_at && (
        <span className={styles.nodeTime}>{formatRelTime(node.created_at)}</span>
      )}
    </button>
  )
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getVisibleNodes(snapshot: Snapshot | null): NodeRecord[] {
  if (!snapshot) return []
  return snapshot.tree_state.node_registry
    .filter((n) => !n.is_superseded)
    .slice()
    .sort((a, b) =>
      a.hierarchical_number.localeCompare(b.hierarchical_number, undefined, { numeric: true }),
    )
}
