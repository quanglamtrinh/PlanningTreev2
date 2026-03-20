import { create } from 'zustand'
import { api, ApiError } from '../api/client'
import type {
  BootstrapStatus,
  NodeDraft,
  NodeRecord,
  NodeStatus,
  PlanningEvent,
  PlanningTurn,
  ProjectSummary,
  Snapshot,
  SplitMode,
} from '../api/types'

const ACTIVE_PROJECT_KEY = 'planningtree.active-project-id'

function readStoredActiveProjectId(): string | null {
  if (typeof window === 'undefined') {
    return null
  }
  return window.localStorage.getItem(ACTIVE_PROJECT_KEY)
}

function writeStoredActiveProjectId(projectId: string | null) {
  if (typeof window === 'undefined') {
    return
  }
  if (projectId) {
    window.localStorage.setItem(ACTIVE_PROJECT_KEY, projectId)
  } else {
    window.localStorage.removeItem(ACTIVE_PROJECT_KEY)
  }
}

function toErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message
  }
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

function resolvePreferredProjectId(
  projects: ProjectSummary[],
  options: {
    storedProjectId?: string | null
    currentProjectId?: string | null
  } = {},
): string | null {
  const { storedProjectId = null, currentProjectId = null } = options

  if (storedProjectId && projects.some((project) => project.id === storedProjectId)) {
    return storedProjectId
  }

  if (currentProjectId && projects.some((project) => project.id === currentProjectId)) {
    return currentProjectId
  }

  return projects[0]?.id ?? null
}

function rootFallback(snapshot: Snapshot | null): string | null {
  if (!snapshot) {
    return null
  }
  return snapshot.tree_state.active_node_id ?? snapshot.tree_state.root_node_id
}

function nodeById(snapshot: Snapshot | null, nodeId: string | null): NodeRecord | null {
  if (!snapshot || !nodeId) {
    return null
  }
  return snapshot.tree_state.node_registry.find((node) => node.node_id === nodeId) ?? null
}

function preserveSelectedNodeId(
  snapshot: Snapshot,
  currentSelectedNodeId: string | null,
): string | null {
  if (
    currentSelectedNodeId &&
    snapshot.tree_state.node_registry.some((node) => node.node_id === currentSelectedNodeId)
  ) {
    return currentSelectedNodeId
  }
  return rootFallback(snapshot)
}

export type PlanningConnectionStatus =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'reconnecting'
export type PlanningSplitMode = SplitMode | null

type ProjectStoreState = {
  hasInitialized: boolean
  isInitializing: boolean
  bootstrap: BootstrapStatus | null
  baseWorkspaceRoot: string | null
  projects: ProjectSummary[]
  activeProjectId: string | null
  snapshot: Snapshot | null
  selectedNodeId: string | null
  nodeDrafts: Record<string, NodeDraft>
  planningHistoryByNode: Record<string, PlanningTurn[]>
  planningConnectionStatus: PlanningConnectionStatus
  activePlanningMode: PlanningSplitMode
  error: string | null
  isWorkspaceSaving: boolean
  isLoadingProjects: boolean
  isLoadingSnapshot: boolean
  isCreatingProject: boolean
  isCreatingNode: boolean
  isSplittingNode: boolean
  isResettingProject: boolean
  splittingNodeId: string | null
  isUpdatingNode: boolean
  isPersistingSelection: boolean
  initialize: () => Promise<void>
  refreshProjects: () => Promise<void>
  setWorkspaceRoot: (path: string) => Promise<void>
  loadProject: (projectId: string) => Promise<void>
  clearActiveProject: () => void
  createProject: (name: string, rootGoal: string) => Promise<void>
  deleteProject: (projectId: string) => Promise<void>
  resetProjectToRoot: () => Promise<void>
  selectNode: (nodeId: string | null, persist?: boolean) => Promise<void>
  stageNodeEdit: (nodeId: string, draft: NodeDraft) => void
  flushNodeDraft: (nodeId: string) => Promise<void>
  createChild: (parentId: string) => Promise<void>
  splitNode: (nodeId: string, mode: SplitMode, confirmReplace?: boolean) => Promise<void>
  loadPlanningHistory: (projectId: string, nodeId: string) => Promise<void>
  applyPlanningEvent: (projectId: string, nodeId: string, event: PlanningEvent) => void
  setPlanningConnectionStatus: (status: PlanningConnectionStatus) => void
  setPlanningNodeBusyState: (nodeId: string, isBusy: boolean) => void
  clearPlanningState: () => void
  patchNodeStatus: (nodeId: string, status: NodeStatus) => void
  clearError: () => void
}

export const useProjectStore = create<ProjectStoreState>((set, get) => {
  async function refreshSnapshot(projectId: string): Promise<Snapshot> {
    const snapshot = await api.getSnapshot(projectId)
    set((state) => ({
      snapshot,
      selectedNodeId: preserveSelectedNodeId(snapshot, state.selectedNodeId),
    }))
    return snapshot
  }

  return {
    hasInitialized: false,
    isInitializing: false,
    bootstrap: null,
    baseWorkspaceRoot: null,
    projects: [],
    activeProjectId: null,
    snapshot: null,
    selectedNodeId: null,
    nodeDrafts: {},
    planningHistoryByNode: {},
    planningConnectionStatus: 'disconnected',
    activePlanningMode: null,
    error: null,
    isWorkspaceSaving: false,
    isLoadingProjects: false,
    isLoadingSnapshot: false,
    isCreatingProject: false,
    isCreatingNode: false,
    isSplittingNode: false,
    isResettingProject: false,
    splittingNodeId: null,
    isUpdatingNode: false,
    isPersistingSelection: false,
    async initialize() {
      if (get().isInitializing || get().hasInitialized) {
        return
      }
      set({ isInitializing: true, error: null })
      try {
        const bootstrap = await api.getBootstrapStatus()
        let baseWorkspaceRoot: string | null = null
        let projects: ProjectSummary[] = []
        if (bootstrap.workspace_configured) {
          const settings = await api.getWorkspaceSettings()
          baseWorkspaceRoot = settings.base_workspace_root
          projects = await api.listProjects()
        }

        const nextProjectId = resolvePreferredProjectId(projects, {
          storedProjectId: readStoredActiveProjectId(),
        })

        if (nextProjectId) {
          writeStoredActiveProjectId(nextProjectId)
        } else {
          writeStoredActiveProjectId(null)
        }

        set({
          bootstrap,
          baseWorkspaceRoot,
          projects,
          hasInitialized: true,
          isInitializing: false,
          activeProjectId: nextProjectId,
        })

        if (nextProjectId) {
          await get().loadProject(nextProjectId)
        }
      } catch (error) {
        set({
          error: toErrorMessage(error),
          hasInitialized: true,
          isInitializing: false,
        })
      }
    },
    async refreshProjects() {
      if (!get().bootstrap?.workspace_configured) {
        writeStoredActiveProjectId(null)
        set({
          projects: [],
          activeProjectId: null,
          snapshot: null,
          selectedNodeId: null,
          planningHistoryByNode: {},
          planningConnectionStatus: 'disconnected',
          activePlanningMode: null,
        })
        return
      }
      set({ isLoadingProjects: true, error: null })
      try {
        const projects = await api.listProjects()
        const currentState = get()
        const nextProjectId = resolvePreferredProjectId(projects, {
          storedProjectId: readStoredActiveProjectId(),
          currentProjectId: currentState.activeProjectId,
        })
        const keepLoadedSnapshot =
          Boolean(nextProjectId) && currentState.snapshot?.project.id === nextProjectId

        set({
          projects,
          activeProjectId: nextProjectId,
          snapshot: keepLoadedSnapshot ? currentState.snapshot : null,
          selectedNodeId: keepLoadedSnapshot ? currentState.selectedNodeId : null,
          nodeDrafts: keepLoadedSnapshot ? currentState.nodeDrafts : {},
          planningHistoryByNode: keepLoadedSnapshot ? currentState.planningHistoryByNode : {},
          planningConnectionStatus: keepLoadedSnapshot
            ? currentState.planningConnectionStatus
            : 'disconnected',
          activePlanningMode: keepLoadedSnapshot ? currentState.activePlanningMode : null,
          isLoadingProjects: false,
        })

        if (!nextProjectId) {
          writeStoredActiveProjectId(null)
          return
        }

        writeStoredActiveProjectId(nextProjectId)

        if (!keepLoadedSnapshot) {
          await get().loadProject(nextProjectId)
        }
      } catch (error) {
        set({ error: toErrorMessage(error), isLoadingProjects: false })
      }
    },
    async setWorkspaceRoot(path: string) {
      set({ isWorkspaceSaving: true, error: null })
      try {
        const settings = await api.setWorkspaceRoot(path)
        const bootstrap = await api.getBootstrapStatus()
        const projects = bootstrap.workspace_configured ? await api.listProjects() : []
        const currentState = get()
        const nextProjectId = resolvePreferredProjectId(projects, {
          storedProjectId: readStoredActiveProjectId(),
          currentProjectId: currentState.activeProjectId,
        })
        const keepLoadedSnapshot =
          Boolean(nextProjectId) && currentState.snapshot?.project.id === nextProjectId

        if (nextProjectId) {
          writeStoredActiveProjectId(nextProjectId)
        } else {
          writeStoredActiveProjectId(null)
        }

        set({
          baseWorkspaceRoot: settings.base_workspace_root,
          bootstrap,
          projects,
          isWorkspaceSaving: false,
          activeProjectId: nextProjectId,
          snapshot: keepLoadedSnapshot ? currentState.snapshot : null,
          selectedNodeId: keepLoadedSnapshot ? currentState.selectedNodeId : null,
          nodeDrafts: keepLoadedSnapshot ? currentState.nodeDrafts : {},
          planningHistoryByNode: keepLoadedSnapshot ? currentState.planningHistoryByNode : {},
          planningConnectionStatus: keepLoadedSnapshot
            ? currentState.planningConnectionStatus
            : 'disconnected',
          activePlanningMode: keepLoadedSnapshot ? currentState.activePlanningMode : null,
        })

        if (nextProjectId && !keepLoadedSnapshot) {
          await get().loadProject(nextProjectId)
        }
      } catch (error) {
        set({ error: toErrorMessage(error), isWorkspaceSaving: false })
        throw error
      }
    },
    async loadProject(projectId: string) {
      const currentState = get()
      const isSameProjectLoaded = currentState.snapshot?.project.id === projectId

      writeStoredActiveProjectId(projectId)
      set({
        isLoadingSnapshot: true,
        error: null,
        activeProjectId: projectId,
        ...(isSameProjectLoaded
          ? {}
          : {
              snapshot: null,
              selectedNodeId: null,
              nodeDrafts: {},
              planningHistoryByNode: {},
              planningConnectionStatus: 'disconnected' as const,
              activePlanningMode: null,
            }),
      })
      try {
        const snapshot = await api.getSnapshot(projectId)
        set({
          activeProjectId: projectId,
          snapshot,
          selectedNodeId: rootFallback(snapshot),
          nodeDrafts: {},
          planningHistoryByNode: {},
          planningConnectionStatus: 'disconnected',
          activePlanningMode: null,
          isLoadingSnapshot: false,
        })
      } catch (error) {
        writeStoredActiveProjectId(null)
        set({
          error: toErrorMessage(error),
          activeProjectId: null,
          snapshot: null,
          selectedNodeId: null,
          nodeDrafts: {},
          planningHistoryByNode: {},
          planningConnectionStatus: 'disconnected',
          activePlanningMode: null,
          isLoadingSnapshot: false,
        })
        throw error
      }
    },
    clearActiveProject() {
      writeStoredActiveProjectId(null)
      set({
        activeProjectId: null,
        snapshot: null,
        selectedNodeId: null,
        nodeDrafts: {},
        planningHistoryByNode: {},
        planningConnectionStatus: 'disconnected',
        activePlanningMode: null,
      })
    },
    async deleteProject(projectId: string) {
      set({ error: null })
      try {
        await api.deleteProject(projectId)
        const wasActive = get().activeProjectId === projectId
        const projects = await api.listProjects()
        if (wasActive) {
          const nextId = projects[0]?.id ?? null
          writeStoredActiveProjectId(nextId)
          set({
            projects,
            activeProjectId: nextId,
            snapshot: null,
            selectedNodeId: null,
            nodeDrafts: {},
            planningHistoryByNode: {},
            planningConnectionStatus: 'disconnected',
            activePlanningMode: null,
          })
          if (nextId) {
            await get().loadProject(nextId)
          }
        } else {
          set({ projects })
        }
      } catch (error) {
        set({ error: toErrorMessage(error) })
        throw error
      }
    },
    async createProject(name: string, rootGoal: string) {
      set({ isCreatingProject: true, error: null })
      try {
        const snapshot = await api.createProject(name, rootGoal)
        const projects = await api.listProjects()
        const projectId = snapshot.project.id
        writeStoredActiveProjectId(projectId)
        set({
          projects,
          activeProjectId: projectId,
          snapshot,
          selectedNodeId: rootFallback(snapshot),
          nodeDrafts: {},
          planningHistoryByNode: {},
          planningConnectionStatus: 'disconnected',
          activePlanningMode: null,
          isCreatingProject: false,
        })
      } catch (error) {
        set({ error: toErrorMessage(error), isCreatingProject: false })
        throw error
      }
    },
    async resetProjectToRoot() {
      const activeProjectId = get().activeProjectId
      if (!activeProjectId) {
        return
      }
      set({ isResettingProject: true, error: null })
      try {
        const snapshot = await api.resetProjectToRoot(activeProjectId)
        set({
          snapshot,
          selectedNodeId: snapshot.tree_state.root_node_id,
          nodeDrafts: {},
          planningHistoryByNode: {},
          planningConnectionStatus: 'disconnected',
          activePlanningMode: null,
          isSplittingNode: false,
          splittingNodeId: null,
          isResettingProject: false,
        })
      } catch (error) {
        set({ error: toErrorMessage(error), isResettingProject: false })
        throw error
      }
    },
    async selectNode(nodeId: string | null, persist = true) {
      set({ selectedNodeId: nodeId })
      const activeProjectId = get().activeProjectId
      if (!persist || !activeProjectId) {
        return
      }
      set({ isPersistingSelection: true, error: null })
      try {
        const snapshot = await api.setActiveNode(activeProjectId, nodeId)
        set({
          snapshot,
          selectedNodeId: rootFallback(snapshot),
          isPersistingSelection: false,
        })
      } catch (error) {
        set({ error: toErrorMessage(error), isPersistingSelection: false })
      }
    },
    stageNodeEdit(nodeId: string, draft: NodeDraft) {
      set((state) => ({
        nodeDrafts: {
          ...state.nodeDrafts,
          [nodeId]: {
            ...state.nodeDrafts[nodeId],
            ...draft,
          },
        },
      }))
    },
    async flushNodeDraft(nodeId: string) {
      const state = get()
      const activeProjectId = state.activeProjectId
      const snapshot = state.snapshot
      const draft = state.nodeDrafts[nodeId]
      const currentNode = nodeById(snapshot, nodeId)

      if (!activeProjectId || !snapshot || !draft || !currentNode) {
        return
      }

      const payload: { title?: string; description?: string } = {}
      if (draft.title !== undefined && draft.title !== currentNode.title) {
        payload.title = draft.title
      }
      if (draft.description !== undefined && draft.description !== currentNode.description) {
        payload.description = draft.description
      }

      if (payload.title === undefined && payload.description === undefined) {
        set((store) => {
          const nextDrafts = { ...store.nodeDrafts }
          delete nextDrafts[nodeId]
          return { nodeDrafts: nextDrafts }
        })
        return
      }

      set({ isUpdatingNode: true, error: null })
      try {
        const nextSnapshot = await api.updateNode(activeProjectId, nodeId, payload)
        set((store) => {
          const nextDrafts = { ...store.nodeDrafts }
          delete nextDrafts[nodeId]
          return {
            snapshot: nextSnapshot,
            selectedNodeId: store.selectedNodeId ?? rootFallback(nextSnapshot),
            nodeDrafts: nextDrafts,
            isUpdatingNode: false,
          }
        })
      } catch (error) {
        set({ error: toErrorMessage(error), isUpdatingNode: false })
        throw error
      }
    },
    async createChild(parentId: string) {
      const activeProjectId = get().activeProjectId
      if (!activeProjectId) {
        return
      }
      set({ isCreatingNode: true, error: null })
      try {
        const snapshot = await api.createChild(activeProjectId, parentId)
        set({
          snapshot,
          selectedNodeId: rootFallback(snapshot),
          nodeDrafts: {},
          isCreatingNode: false,
        })
      } catch (error) {
        set({ error: toErrorMessage(error), isCreatingNode: false })
        throw error
      }
    },
    async splitNode(nodeId: string, mode: SplitMode, confirmReplace = false) {
      const activeProjectId = get().activeProjectId
      if (!activeProjectId) {
        return
      }
      set({ isSplittingNode: true, splittingNodeId: nodeId, activePlanningMode: mode, error: null })
      try {
        await api.splitNode(activeProjectId, nodeId, mode, confirmReplace)
      } catch (error) {
        set({
          error: toErrorMessage(error),
          isSplittingNode: false,
          splittingNodeId: null,
          activePlanningMode: null,
        })
        throw error
      }
    },
    async loadPlanningHistory(projectId: string, nodeId: string) {
      try {
        const response = await api.getPlanningHistory(projectId, nodeId)
        set((state) => ({
          planningHistoryByNode: {
            ...state.planningHistoryByNode,
            [nodeId]: response.turns,
          },
        }))
      } catch (error) {
        set({ error: toErrorMessage(error) })
        throw error
      }
    },
    applyPlanningEvent(projectId: string, nodeId: string, event: PlanningEvent) {
      if (event.node_id !== nodeId) {
        return
      }
      if (event.type === 'planning_turn_started') {
        set({ isSplittingNode: true, splittingNodeId: nodeId, activePlanningMode: event.mode })
        return
      }
      if (event.type === 'planning_tool_call') {
        set((state) => {
          const currentTurns = state.planningHistoryByNode[nodeId] ?? []
          const nextTurns = [
            ...currentTurns.filter(
              (turn) => !(turn.role === 'tool_call' && turn.turn_id === event.turn_id),
            ),
            {
              turn_id: event.turn_id,
              role: 'tool_call' as const,
              is_inherited: false,
              origin_node_id: nodeId,
              tool_name: event.tool_name,
              arguments: {
                kind: event.kind ?? undefined,
                payload: event.payload ?? undefined,
              },
              timestamp: new Date().toISOString(),
            },
          ]
          return {
            planningHistoryByNode: {
              ...state.planningHistoryByNode,
              [nodeId]: nextTurns,
            },
          }
        })
        return
      }
      if (event.type === 'planning_turn_completed' || event.type === 'planning_turn_failed') {
        set({
          isSplittingNode: false,
          splittingNodeId: null,
          activePlanningMode: null,
          error: event.type === 'planning_turn_failed' ? event.message : null,
        })
        void get().loadPlanningHistory(projectId, nodeId)
        void refreshSnapshot(projectId).catch((error) => {
          set({ error: toErrorMessage(error) })
        })
      }
    },
    setPlanningConnectionStatus(status: PlanningConnectionStatus) {
      set({ planningConnectionStatus: status })
    },
    setPlanningNodeBusyState(nodeId: string, isBusy: boolean) {
      set((state) => {
        if (isBusy) {
          if (state.isSplittingNode && state.splittingNodeId === nodeId) {
            return {}
          }
          return {
            isSplittingNode: true,
            splittingNodeId: nodeId,
          }
        }

        if (state.splittingNodeId !== nodeId) {
          return {}
        }

        return {
          isSplittingNode: false,
          splittingNodeId: null,
          activePlanningMode: null,
        }
      })
    },
    clearPlanningState() {
      set({
        planningConnectionStatus: 'disconnected',
        planningHistoryByNode: {},
        isSplittingNode: false,
        splittingNodeId: null,
        activePlanningMode: null,
      })
    },
    patchNodeStatus(nodeId: string, status: NodeStatus) {
      set((state) => {
        if (!state.snapshot) {
          return {}
        }
        let didChange = false
        const nodeRegistry = state.snapshot.tree_state.node_registry.map((node) => {
          if (node.node_id !== nodeId || node.status === status) {
            return node
          }
          didChange = true
          return { ...node, status }
        })
        if (!didChange) {
          return {}
        }
        return {
          snapshot: {
            ...state.snapshot,
            tree_state: {
              ...state.snapshot.tree_state,
              node_registry: nodeRegistry,
            },
          },
        }
      })
    },
    clearError() {
      set({ error: null })
    },
  }
})
