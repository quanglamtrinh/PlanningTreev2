import { create } from 'zustand'
import { api, ApiError } from '../api/client'
import type {
  AgentActivity,
  AgentEvent,
  BootstrapStatus,
  NodeBriefing,
  NodeDraft,
  NodeDocuments,
  NodeRecord,
  NodeSpec,
  NodeStatus,
  NodeTask,
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

function preserveSelectedNodeId(snapshot: Snapshot, currentSelectedNodeId: string | null): string | null {
  if (
    currentSelectedNodeId &&
    snapshot.tree_state.node_registry.some((node) => node.node_id === currentSelectedNodeId)
  ) {
    return currentSelectedNodeId
  }
  return rootFallback(snapshot)
}

export type PlanningConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'reconnecting'
export type PlanningSplitMode = SplitMode | null
export type AgentConnectionStatus = PlanningConnectionStatus

function markPerformance(name: string) {
  if (typeof window === 'undefined' || typeof window.performance?.mark !== 'function') {
    return
  }
  window.performance.mark(name)
}

function toAgentActivity(event: AgentEvent): AgentActivity {
  return {
    operation: event.operation,
    stage: event.stage,
    message: event.message,
    status: event.type,
    timestamp: event.timestamp,
  }
}

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
  documentsByNode: Record<string, NodeDocuments | undefined>
  planningHistoryByNode: Record<string, PlanningTurn[]>
  agentActivityByNode: Record<string, AgentActivity | undefined>
  planningConnectionStatus: PlanningConnectionStatus
  agentConnectionStatus: AgentConnectionStatus
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
  isLoadingDocuments: boolean
  isUpdatingDocument: boolean
  isGeneratingSpec: boolean
  isConfirmingNode: boolean
  isCompletingNode: boolean
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
  splitNode: (
    nodeId: string,
    mode: SplitMode,
    confirmReplace?: boolean,
  ) => Promise<void>
  startPlan: (nodeId: string) => Promise<void>
  executeNode: (nodeId: string) => Promise<void>
  loadNodeDocuments: (nodeId: string) => Promise<NodeDocuments | null>
  updateNodeTask: (nodeId: string, payload: Partial<NodeTask>) => Promise<void>
  updateNodeBriefing: (nodeId: string, payload: Partial<NodeBriefing>) => Promise<void>
  updateNodeSpec: (nodeId: string, payload: Partial<NodeSpec>) => Promise<void>
  confirmTask: (nodeId: string) => Promise<void>
  confirmBriefing: (nodeId: string) => Promise<void>
  confirmSpec: (nodeId: string) => Promise<void>
  generateNodeSpec: (nodeId: string) => Promise<void>
  resyncNodeArtifacts: (nodeId: string) => Promise<void>
  loadPlanningHistory: (projectId: string, nodeId: string) => Promise<void>
  applyPlanningEvent: (projectId: string, nodeId: string, event: PlanningEvent) => void
  setPlanningConnectionStatus: (status: PlanningConnectionStatus) => void
  setPlanningNodeBusyState: (nodeId: string, isBusy: boolean) => void
  clearPlanningState: () => void
  applyAgentEvent: (projectId: string, nodeId: string, event: AgentEvent) => void
  setAgentConnectionStatus: (status: AgentConnectionStatus) => void
  clearAgentState: () => void
  completeNode: (nodeId: string) => Promise<void>
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

  async function syncNodeDocuments(projectId: string, nodeId: string): Promise<NodeDocuments> {
    const documents = await api.getNodeDocuments(projectId, nodeId)
    set((state) => ({
      documentsByNode: {
        ...state.documentsByNode,
        [nodeId]: documents,
      },
    }))
    return documents
  }

  async function resyncNodeArtifactsInternal(projectId: string, nodeId: string): Promise<void> {
    await Promise.all([refreshSnapshot(projectId), syncNodeDocuments(projectId, nodeId)])
  }

  return ({
  hasInitialized: false,
  isInitializing: false,
  bootstrap: null,
  baseWorkspaceRoot: null,
  projects: [],
  activeProjectId: null,
  snapshot: null,
  selectedNodeId: null,
  nodeDrafts: {},
  documentsByNode: {},
  planningHistoryByNode: {},
  agentActivityByNode: {},
  planningConnectionStatus: 'disconnected',
  agentConnectionStatus: 'disconnected',
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
  isLoadingDocuments: false,
  isUpdatingDocument: false,
  isGeneratingSpec: false,
  isConfirmingNode: false,
  isCompletingNode: false,
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
        documentsByNode: {},
        agentActivityByNode: {},
        agentConnectionStatus: 'disconnected',
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
        documentsByNode: {},
        planningHistoryByNode: {},
        agentActivityByNode: {},
        planningConnectionStatus: 'disconnected',
        agentConnectionStatus: 'disconnected',
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
        documentsByNode: keepLoadedSnapshot ? currentState.documentsByNode : {},
        planningHistoryByNode: keepLoadedSnapshot ? currentState.planningHistoryByNode : {},
        agentActivityByNode: keepLoadedSnapshot ? currentState.agentActivityByNode : {},
        planningConnectionStatus: keepLoadedSnapshot ? currentState.planningConnectionStatus : 'disconnected',
        agentConnectionStatus: keepLoadedSnapshot ? currentState.agentConnectionStatus : 'disconnected',
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
        documentsByNode: keepLoadedSnapshot ? currentState.documentsByNode : {},
        planningHistoryByNode: keepLoadedSnapshot ? currentState.planningHistoryByNode : {},
        agentActivityByNode: keepLoadedSnapshot ? currentState.agentActivityByNode : {},
        planningConnectionStatus: keepLoadedSnapshot ? currentState.planningConnectionStatus : 'disconnected',
        agentConnectionStatus: keepLoadedSnapshot ? currentState.agentConnectionStatus : 'disconnected',
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
            documentsByNode: {},
            planningHistoryByNode: {},
            agentActivityByNode: {},
            planningConnectionStatus: 'disconnected' as const,
            agentConnectionStatus: 'disconnected' as const,
            activePlanningMode: null,
          }),
    })
    try {
      const snapshot = await api.getSnapshot(projectId)
      const nextSelected = rootFallback(snapshot)
      set({
        activeProjectId: projectId,
        snapshot,
        selectedNodeId: nextSelected,
        nodeDrafts: {},
        documentsByNode: {},
        planningHistoryByNode: {},
        agentActivityByNode: {},
        planningConnectionStatus: 'disconnected',
        agentConnectionStatus: 'disconnected',
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
        documentsByNode: {},
        planningHistoryByNode: {},
        agentActivityByNode: {},
        planningConnectionStatus: 'disconnected',
        agentConnectionStatus: 'disconnected',
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
      documentsByNode: {},
      planningHistoryByNode: {},
      agentActivityByNode: {},
      planningConnectionStatus: 'disconnected',
      agentConnectionStatus: 'disconnected',
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
          documentsByNode: {},
          planningHistoryByNode: {},
          agentActivityByNode: {},
          planningConnectionStatus: 'disconnected',
          agentConnectionStatus: 'disconnected',
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
        documentsByNode: {},
        planningHistoryByNode: {},
        agentActivityByNode: {},
        planningConnectionStatus: 'disconnected',
        agentConnectionStatus: 'disconnected',
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
        documentsByNode: {},
        planningHistoryByNode: {},
        agentActivityByNode: {},
        planningConnectionStatus: 'disconnected',
        agentConnectionStatus: 'disconnected',
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
        documentsByNode: {},
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
  async startPlan(nodeId: string) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    markPerformance('agent_click')
    set({ error: null })
    try {
      await api.startPlan(activeProjectId, nodeId)
      await get().resyncNodeArtifacts(nodeId)
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  async executeNode(nodeId: string) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    set({ error: null })
    try {
      await api.executeNode(activeProjectId, nodeId)
      await Promise.all([refreshSnapshot(activeProjectId), syncNodeDocuments(activeProjectId, nodeId)])
    } catch (error) {
      set({ error: toErrorMessage(error) })
      throw error
    }
  },
  async loadNodeDocuments(nodeId: string) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return null
    }
    set({ isLoadingDocuments: true, error: null })
    try {
      const documents = await syncNodeDocuments(activeProjectId, nodeId)
      set({ isLoadingDocuments: false })
      return documents
    } catch (error) {
      set({ error: toErrorMessage(error), isLoadingDocuments: false })
      throw error
    }
  },
  async updateNodeTask(nodeId: string, payload: Partial<NodeTask>) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    set({ isUpdatingDocument: true, error: null })
    try {
      await api.updateNodeTask(activeProjectId, nodeId, payload)
      await Promise.all([refreshSnapshot(activeProjectId), syncNodeDocuments(activeProjectId, nodeId)])
      set({ isUpdatingDocument: false })
    } catch (error) {
      set({ error: toErrorMessage(error), isUpdatingDocument: false })
      throw error
    }
  },
  async updateNodeBriefing(nodeId: string, payload: Partial<NodeBriefing>) {
    void nodeId
    void payload
    const error = new Error('Brief is read-only.')
    set({ error: toErrorMessage(error) })
    throw error
  },
  async updateNodeSpec(nodeId: string, payload: Partial<NodeSpec>) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    set({ isUpdatingDocument: true, error: null })
    try {
      await api.updateNodeSpec(activeProjectId, nodeId, payload)
      await Promise.all([refreshSnapshot(activeProjectId), syncNodeDocuments(activeProjectId, nodeId)])
      set({ isUpdatingDocument: false })
    } catch (error) {
      set({ error: toErrorMessage(error), isUpdatingDocument: false })
      throw error
    }
  },
  async confirmTask(nodeId: string) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    markPerformance('agent_click')
    set({ isConfirmingNode: true, error: null })
    try {
      await api.confirmTask(activeProjectId, nodeId)
      await get().resyncNodeArtifacts(nodeId)
      set({ isConfirmingNode: false })
    } catch (error) {
      set({ error: toErrorMessage(error), isConfirmingNode: false })
      throw error
    }
  },
  async confirmBriefing(nodeId: string) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    set({ isConfirmingNode: true, error: null })
    try {
      await api.confirmBriefing(activeProjectId, nodeId)
      await Promise.all([refreshSnapshot(activeProjectId), syncNodeDocuments(activeProjectId, nodeId)])
      set({ isConfirmingNode: false })
    } catch (error) {
      set({ error: toErrorMessage(error), isConfirmingNode: false })
      throw error
    }
  },
  async confirmSpec(nodeId: string) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    set({ isConfirmingNode: true, error: null })
    try {
      await api.confirmSpec(activeProjectId, nodeId)
      await Promise.all([refreshSnapshot(activeProjectId), syncNodeDocuments(activeProjectId, nodeId)])
      set({ isConfirmingNode: false })
    } catch (error) {
      set({ error: toErrorMessage(error), isConfirmingNode: false })
      throw error
    }
  },
  async generateNodeSpec(nodeId: string) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    markPerformance('agent_click')
    set({ isGeneratingSpec: true, error: null })
    try {
      await api.generateNodeSpec(activeProjectId, nodeId)
      await get().resyncNodeArtifacts(nodeId)
      set({ isGeneratingSpec: false })
    } catch (error) {
      await get().resyncNodeArtifacts(nodeId).catch(() => undefined)
      set({ error: toErrorMessage(error), isGeneratingSpec: false })
      throw error
    }
  },
  async resyncNodeArtifacts(nodeId: string) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    await resyncNodeArtifactsInternal(activeProjectId, nodeId)
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
      void get().resyncNodeArtifacts(nodeId)
      void api
        .getSnapshot(projectId)
        .then((snapshot) => {
          set((state) => ({
            snapshot,
            selectedNodeId: preserveSelectedNodeId(snapshot, state.selectedNodeId),
            nodeDrafts: {},
          }))
        })
        .catch((error) => {
          set({ error: toErrorMessage(error) })
        })
      return
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
  applyAgentEvent(projectId: string, nodeId: string, event: AgentEvent) {
    if (event.node_id !== nodeId) {
      return
    }
    set((state) => ({
      agentActivityByNode: {
        ...state.agentActivityByNode,
        [nodeId]: toAgentActivity(event),
      },
    }))
    if (event.type === 'operation_started' || event.type === 'operation_progress') {
      markPerformance('agent_feedback_visible')
    }
    if (event.type === 'operation_completed' || event.type === 'operation_failed') {
      markPerformance('agent_completed')
    }
    void resyncNodeArtifactsInternal(projectId, nodeId).catch(() => undefined)
  },
  setAgentConnectionStatus(status: AgentConnectionStatus) {
    set({ agentConnectionStatus: status })
  },
  clearAgentState() {
    set({
      agentConnectionStatus: 'disconnected',
      agentActivityByNode: {},
    })
  },
  async completeNode(nodeId: string) {
    const activeProjectId = get().activeProjectId
    if (!activeProjectId) {
      return
    }
    set({ isCompletingNode: true, error: null })
    try {
      const snapshot = await api.completeNode(activeProjectId, nodeId)
      set({
        snapshot,
        selectedNodeId: rootFallback(snapshot),
        nodeDrafts: {},
        isCompletingNode: false,
      })
    } catch (error) {
      set({ error: toErrorMessage(error), isCompletingNode: false })
      throw error
    }
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
  })
})
