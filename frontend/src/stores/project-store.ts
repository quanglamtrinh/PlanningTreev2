import { create } from 'zustand'
import { api, ApiError } from '../api/client'
import type {
  BootstrapStatus,
  NodeDraft,
  ProjectSummary,
  Snapshot,
  SplitJobStatus,
  SplitMode,
} from '../api/types'

const ACTIVE_PROJECT_KEY = 'planningtree.active-project-id'
const LEGACY_PROJECT_MESSAGE =
  'This project uses a removed legacy schema. Delete it or recreate it before continuing.'
const SPLIT_POLL_INTERVAL_MS = 1500

let splitPollTimer: ReturnType<typeof globalThis.setInterval> | null = null
let splitPollProjectId: string | null = null

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
    if (error.code === 'legacy_project_unsupported') {
      return LEGACY_PROJECT_MESSAGE
    }
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

export type ProjectStoreState = {
  hasInitialized: boolean
  isInitializing: boolean
  bootstrap: BootstrapStatus | null
  projects: ProjectSummary[]
  activeProjectId: string | null
  snapshot: Snapshot | null
  selectedNodeId: string | null
  nodeDrafts: Record<string, NodeDraft>
  splitStatus: SplitJobStatus
  splitJobId: string | null
  splitNodeId: string | null
  splitMode: SplitMode | null
  error: string | null
  isLoadingProjects: boolean
  isLoadingSnapshot: boolean
  isAttachingProject: boolean
  isCreatingNode: boolean
  isResettingProject: boolean
  isUpdatingNode: boolean
  isPersistingSelection: boolean
  initialize: () => Promise<void>
  refreshProjects: () => Promise<void>
  attachProjectFolder: (folderPath: string) => Promise<void>
  loadProject: (projectId: string) => Promise<void>
  clearActiveProject: () => void
  deleteProject: (projectId: string) => Promise<void>
  resetProjectToRoot: () => Promise<void>
  selectNode: (nodeId: string | null, persist?: boolean) => Promise<void>
  stageNodeEdit: (nodeId: string, draft: NodeDraft) => void
  flushNodeDraft: (nodeId: string) => Promise<void>
  createChild: (parentId: string) => Promise<void>
  splitNode: (nodeId: string, mode: SplitMode) => Promise<void>
  refreshSplitStatus: (projectId?: string) => Promise<void>
  clearError: () => void
}

export const useProjectStore = create<ProjectStoreState>((set, get) => {
  async function refreshSnapshot(projectId: string): Promise<Snapshot> {
    const snapshot = await api.getSnapshot(projectId)
    set((state) => ({
      snapshot,
      selectedNodeId: rootFallback(snapshot) ?? state.selectedNodeId,
    }))
    return snapshot
  }

  return {
    hasInitialized: false,
    isInitializing: false,
    bootstrap: null,
    projects: [],
    activeProjectId: null,
    snapshot: null,
    selectedNodeId: null,
    nodeDrafts: {},
    splitStatus: 'idle',
    splitJobId: null,
    splitNodeId: null,
    splitMode: null,
    error: null,
    isLoadingProjects: false,
    isLoadingSnapshot: false,
    isAttachingProject: false,
    isCreatingNode: false,
    isResettingProject: false,
    isUpdatingNode: false,
    isPersistingSelection: false,
    async initialize() {
      if (get().isInitializing || get().hasInitialized) {
        return
      }
      set({ isInitializing: true, error: null })
      try {
        const [bootstrap, projects] = await Promise.all([
          api.getBootstrapStatus(),
          api.listProjects(),
        ])

        const nextProjectId = resolvePreferredProjectId(projects, {
          storedProjectId: readStoredActiveProjectId(),
        })

        writeStoredActiveProjectId(nextProjectId)

        set({
          bootstrap,
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

        if (!keepLoadedSnapshot) {
          stopSplitPolling()
        }

        writeStoredActiveProjectId(nextProjectId)
        set({
          projects,
          activeProjectId: nextProjectId,
          snapshot: keepLoadedSnapshot ? currentState.snapshot : null,
          selectedNodeId: keepLoadedSnapshot ? currentState.selectedNodeId : null,
          nodeDrafts: keepLoadedSnapshot ? currentState.nodeDrafts : {},
          splitStatus: keepLoadedSnapshot ? currentState.splitStatus : 'idle',
          splitJobId: keepLoadedSnapshot ? currentState.splitJobId : null,
          splitNodeId: keepLoadedSnapshot ? currentState.splitNodeId : null,
          splitMode: keepLoadedSnapshot ? currentState.splitMode : null,
          isLoadingProjects: false,
        })

        if (nextProjectId && !keepLoadedSnapshot) {
          await get().loadProject(nextProjectId)
        }
      } catch (error) {
        set({ error: toErrorMessage(error), isLoadingProjects: false })
      }
    },
    async attachProjectFolder(folderPath: string) {
      set({ isAttachingProject: true, error: null })
      try {
        const snapshot = await api.attachProjectFolder(folderPath)
        const projects = await api.listProjects()
        const projectId = snapshot.project.id
        stopSplitPolling()
        writeStoredActiveProjectId(projectId)
        set({
          projects,
          activeProjectId: projectId,
          snapshot,
          selectedNodeId: rootFallback(snapshot),
          nodeDrafts: {},
          splitStatus: 'idle',
          splitJobId: null,
          splitNodeId: null,
          splitMode: null,
          isAttachingProject: false,
        })
      } catch (error) {
        set({ error: toErrorMessage(error), isAttachingProject: false })
        throw error
      }
    },
    async loadProject(projectId: string) {
      stopSplitPolling()
      writeStoredActiveProjectId(projectId)
      set({
        isLoadingSnapshot: true,
        error: null,
        activeProjectId: projectId,
        snapshot: null,
        selectedNodeId: null,
        nodeDrafts: {},
        splitStatus: 'idle',
        splitJobId: null,
        splitNodeId: null,
        splitMode: null,
      })
      try {
        const snapshot = await api.getSnapshot(projectId)
        set({
          activeProjectId: projectId,
          snapshot,
          selectedNodeId: rootFallback(snapshot),
          nodeDrafts: {},
          isLoadingSnapshot: false,
        })
        await get().refreshSplitStatus(projectId)
      } catch (error) {
        set({
          error: toErrorMessage(error),
          activeProjectId: projectId,
          snapshot: null,
          selectedNodeId: null,
          nodeDrafts: {},
          splitStatus: 'idle',
          splitJobId: null,
          splitNodeId: null,
          splitMode: null,
          isLoadingSnapshot: false,
        })
        throw error
      }
    },
    clearActiveProject() {
      stopSplitPolling()
      writeStoredActiveProjectId(null)
      set({
        activeProjectId: null,
        snapshot: null,
        selectedNodeId: null,
        nodeDrafts: {},
        splitStatus: 'idle',
        splitJobId: null,
        splitNodeId: null,
        splitMode: null,
      })
    },
    async deleteProject(projectId: string) {
      set({ error: null })
      try {
        await api.deleteProject(projectId)
        const wasActive = get().activeProjectId === projectId
        const projects = await api.listProjects()
        if (wasActive) {
          stopSplitPolling()
          const nextId = projects[0]?.id ?? null
          writeStoredActiveProjectId(nextId)
          set({
            projects,
            activeProjectId: nextId,
            snapshot: null,
            selectedNodeId: null,
            nodeDrafts: {},
            splitStatus: 'idle',
            splitJobId: null,
            splitNodeId: null,
            splitMode: null,
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
      const currentNode = snapshot?.tree_state.node_registry.find((node) => node.node_id === nodeId) ?? null

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
    async splitNode(nodeId: string, mode: SplitMode) {
      const activeProjectId = get().activeProjectId
      if (!activeProjectId) {
        return
      }
      set({
        error: null,
        splitStatus: 'active',
        splitJobId: null,
        splitNodeId: nodeId,
        splitMode: mode,
      })
      try {
        const accepted = await api.splitNode(activeProjectId, nodeId, mode)
        if (get().activeProjectId !== activeProjectId) {
          return
        }
        set({
          splitStatus: 'active',
          splitJobId: accepted.job_id,
          splitNodeId: accepted.node_id,
          splitMode: accepted.mode,
        })
        ensureSplitPolling(activeProjectId)
        void get().refreshSplitStatus(activeProjectId)
      } catch (error) {
        stopSplitPolling()
        set({
          error: toErrorMessage(error),
          splitStatus: 'idle',
          splitJobId: null,
          splitNodeId: null,
          splitMode: null,
        })
        throw error
      }
    },
    async refreshSplitStatus(projectId?: string) {
      const targetProjectId = projectId ?? get().activeProjectId
      if (!targetProjectId) {
        return
      }

      try {
        const response = await api.getSplitStatus(targetProjectId)
        if (get().activeProjectId !== targetProjectId) {
          return
        }

        const previousStatus = get().splitStatus
        if (response.status === 'active') {
          ensureSplitPolling(targetProjectId)
          set({
            splitStatus: 'active',
            splitJobId: response.job_id,
            splitNodeId: response.node_id,
            splitMode: response.mode,
          })
          return
        }

        stopSplitPolling()
        if (response.status === 'failed') {
          set({
            splitStatus: 'failed',
            splitJobId: response.job_id,
            splitNodeId: null,
            splitMode: null,
            error: response.error ?? 'Split failed.',
          })
          return
        }

        set({
          splitStatus: 'idle',
          splitJobId: null,
          splitNodeId: null,
          splitMode: null,
        })
        if (previousStatus === 'active') {
          await refreshSnapshot(targetProjectId)
        }
      } catch (error) {
        if (get().activeProjectId !== targetProjectId) {
          return
        }
        stopSplitPolling()
        set({
          error: toErrorMessage(error),
          splitStatus: 'idle',
          splitJobId: null,
          splitNodeId: null,
          splitMode: null,
        })
      }
    },
    clearError() {
      set({ error: null })
    },
  }
})

function stopSplitPolling() {
  if (splitPollTimer !== null) {
    globalThis.clearInterval(splitPollTimer)
    splitPollTimer = null
  }
  splitPollProjectId = null
}

function ensureSplitPolling(projectId: string) {
  if (typeof window === 'undefined') {
    return
  }
  if (splitPollTimer !== null && splitPollProjectId === projectId) {
    return
  }
  stopSplitPolling()
  splitPollProjectId = projectId
  splitPollTimer = globalThis.setInterval(() => {
    void useProjectStore.getState().refreshSplitStatus(projectId)
  }, SPLIT_POLL_INTERVAL_MS)
}
