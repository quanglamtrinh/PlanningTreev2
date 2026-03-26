import { create } from 'zustand'
import type { DetailState, Snapshot } from '../api/types'
import { api } from '../api/client'
import { mergeMockDetailState } from '../dev/mockDetailState'
import { useProjectStore } from './project-store'

const EXECUTION_POLL_INTERVAL_MS = 1000

type DetailStateStoreState = {
  /** Keyed by `${projectId}::${nodeId}` */
  entries: Record<string, DetailState>
  loading: Record<string, boolean>
  errors: Record<string, string>
  /** Finish Task in flight */
  finishingTask: Record<string, boolean>
  /** Reset workspace in flight */
  resettingWorkspace: Record<string, boolean>

  loadDetailState: (projectId: string, nodeId: string) => Promise<void>
  refreshExecutionState: (projectId: string, nodeId: string) => Promise<void>
  confirmFrame: (projectId: string, nodeId: string) => Promise<DetailState>
  confirmSpec: (projectId: string, nodeId: string) => Promise<DetailState>
  finishTask: (projectId: string, nodeId: string) => Promise<void>
  acceptLocalReview: (projectId: string, nodeId: string, summary: string) => Promise<string | null>
  acceptRollupReview: (projectId: string, reviewNodeId: string) => Promise<void>
  initGit: (projectId: string) => Promise<void>
  resetWorkspace: (projectId: string, nodeId: string, target: 'initial' | 'head') => Promise<void>
  reset: () => void
}

function stateKey(projectId: string, nodeId: string): string {
  return `${projectId}::${nodeId}`
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message
  return String(error)
}

function snapshotContainsNode(snapshot: Snapshot, nodeId: string | null | undefined): boolean {
  if (!nodeId) {
    return false
  }
  return snapshot.tree_state.node_registry.some((node) => node.node_id === nodeId)
}

async function syncProjectSnapshot(
  projectId: string,
  preferredSelectedNodeId?: string | null,
): Promise<Snapshot | null> {
  try {
    const snapshot = await api.getSnapshot(projectId)
    useProjectStore.setState((prev) => ({
      snapshot,
      selectedNodeId:
        (preferredSelectedNodeId && snapshotContainsNode(snapshot, preferredSelectedNodeId))
          ? preferredSelectedNodeId
          : (prev.selectedNodeId && snapshotContainsNode(snapshot, prev.selectedNodeId))
            ? prev.selectedNodeId
            : snapshot.tree_state.active_node_id ?? snapshot.tree_state.root_node_id,
    }))
    return snapshot
  } catch {
    return null
  }
}

const executionPollTimers = new Map<string, ReturnType<typeof globalThis.setTimeout>>()

function stopExecutionPolling(key: string) {
  const timer = executionPollTimers.get(key)
  if (timer !== undefined) {
    globalThis.clearTimeout(timer)
    executionPollTimers.delete(key)
  }
}

function stopAllExecutionPolling() {
  for (const key of executionPollTimers.keys()) {
    stopExecutionPolling(key)
  }
}

export const useDetailStateStore = create<DetailStateStoreState>((set, get) => ({
  entries: {},
  loading: {},
  errors: {},
  finishingTask: {},
  resettingWorkspace: {},

  async loadDetailState(projectId: string, nodeId: string) {
    const key = stateKey(projectId, nodeId)
    if (get().loading[key]) return
    set((s) => ({ loading: { ...s.loading, [key]: true }, errors: { ...s.errors, [key]: '' } }))
    try {
      const raw = await api.getDetailState(projectId, nodeId)
      const state = mergeMockDetailState(raw)
      set((s) => ({
        entries: { ...s.entries, [key]: state },
        loading: { ...s.loading, [key]: false },
        errors: { ...s.errors, [key]: '' },
      }))
      if (state.execution_status === 'executing') {
        if (!executionPollTimers.has(key)) {
          const timer = globalThis.setTimeout(() => {
            executionPollTimers.delete(key)
            void get().refreshExecutionState(projectId, nodeId)
          }, EXECUTION_POLL_INTERVAL_MS)
          executionPollTimers.set(key, timer)
        }
      } else {
        stopExecutionPolling(key)
      }
    } catch (error) {
      set((s) => ({
        loading: { ...s.loading, [key]: false },
        errors: { ...s.errors, [key]: toErrorMessage(error) },
      }))
      stopExecutionPolling(key)
    }
  },

  async refreshExecutionState(projectId: string, nodeId: string) {
    const key = stateKey(projectId, nodeId)
    stopExecutionPolling(key)
    try {
      const raw = await api.getDetailState(projectId, nodeId)
      const state = mergeMockDetailState(raw)
      set((s) => ({
        entries: { ...s.entries, [key]: state },
        errors: { ...s.errors, [key]: '' },
      }))
      if (state.execution_status === 'executing') {
        const timer = globalThis.setTimeout(() => {
          executionPollTimers.delete(key)
          void get().refreshExecutionState(projectId, nodeId)
        }, EXECUTION_POLL_INTERVAL_MS)
        executionPollTimers.set(key, timer)
      } else {
        void syncProjectSnapshot(projectId)
      }
    } catch (error) {
      set((s) => ({
        errors: { ...s.errors, [key]: toErrorMessage(error) },
      }))
    }
  },

  async confirmFrame(projectId: string, nodeId: string) {
    const raw = await api.confirmFrame(projectId, nodeId)
    const state = mergeMockDetailState(raw)
    const key = stateKey(projectId, nodeId)
    set((s) => ({ entries: { ...s.entries, [key]: state }, errors: { ...s.errors, [key]: '' } }))
    return state
  },

  async confirmSpec(projectId: string, nodeId: string) {
    const raw = await api.confirmSpec(projectId, nodeId)
    const state = mergeMockDetailState(raw)
    const key = stateKey(projectId, nodeId)
    set((s) => ({ entries: { ...s.entries, [key]: state }, errors: { ...s.errors, [key]: '' } }))
    return state
  },

  async finishTask(projectId: string, nodeId: string) {
    const key = stateKey(projectId, nodeId)
    set((s) => ({
      finishingTask: { ...s.finishingTask, [key]: true },
      errors: { ...s.errors, [key]: '' },
    }))
    try {
      const raw = await api.finishTask(projectId, nodeId)
      const state = mergeMockDetailState(raw)
      set((s) => ({
        entries: { ...s.entries, [key]: state },
        errors: { ...s.errors, [key]: '' },
      }))
      void syncProjectSnapshot(projectId)
      if (state.execution_status === 'executing') {
        stopExecutionPolling(key)
        const timer = globalThis.setTimeout(() => {
          executionPollTimers.delete(key)
          void get().refreshExecutionState(projectId, nodeId)
        }, EXECUTION_POLL_INTERVAL_MS)
        executionPollTimers.set(key, timer)
      } else {
        stopExecutionPolling(key)
      }
    } catch (error) {
      set((s) => ({
        errors: { ...s.errors, [key]: toErrorMessage(error) },
      }))
      // Reload detail-state so git_blocker_message banner shows structured blocker
      void get().loadDetailState(projectId, nodeId)
    } finally {
      set((s) => ({ finishingTask: { ...s.finishingTask, [key]: false } }))
    }
  },

  async acceptLocalReview(projectId: string, nodeId: string, summary: string) {
    const key = stateKey(projectId, nodeId)
    try {
      const response = await api.acceptLocalReview(projectId, nodeId, summary)
      const raw = await api.getDetailState(projectId, nodeId)
      const state = mergeMockDetailState(raw)
      set((s) => ({
        entries: { ...s.entries, [key]: state },
        errors: { ...s.errors, [key]: '' },
      }))
      await syncProjectSnapshot(projectId, response.activated_sibling_id)
      return response.activated_sibling_id
    } catch (error) {
      throw error
    }
  },

  async acceptRollupReview(projectId: string, reviewNodeId: string) {
    const key = stateKey(projectId, reviewNodeId)
    try {
      await api.acceptRollupReview(projectId, reviewNodeId)

      const reviewRaw = await api.getDetailState(projectId, reviewNodeId)
      const reviewState = mergeMockDetailState(reviewRaw)
      set((s) => ({
        entries: { ...s.entries, [key]: reviewState },
        errors: { ...s.errors, [key]: '' },
      }))

      const snapshot = await syncProjectSnapshot(projectId)
      const parentNodeId = snapshot?.tree_state.node_registry.find(
        (node) => node.review_node_id === reviewNodeId,
      )?.node_id

      if (parentNodeId) {
        const parentKey = stateKey(projectId, parentNodeId)
        const parentRaw = await api.getDetailState(projectId, parentNodeId)
        const parentState = mergeMockDetailState(parentRaw)
        set((s) => ({
          entries: { ...s.entries, [parentKey]: parentState },
          errors: { ...s.errors, [parentKey]: '' },
        }))
      }
    } catch (error) {
      set((s) => ({
        errors: { ...s.errors, [key]: toErrorMessage(error) },
      }))
    }
  },

  async initGit(projectId: string) {
    await api.initGit(projectId)
    await useProjectStore.getState().refreshProjects()
  },

  async resetWorkspace(projectId: string, nodeId: string, target: 'initial' | 'head') {
    const key = stateKey(projectId, nodeId)
    set((s) => ({ resettingWorkspace: { ...s.resettingWorkspace, [key]: true } }))
    try {
      await api.resetWorkspace(projectId, nodeId, target)
      await get().loadDetailState(projectId, nodeId)
      void syncProjectSnapshot(projectId)
    } finally {
      set((s) => ({ resettingWorkspace: { ...s.resettingWorkspace, [key]: false } }))
    }
  },

  reset() {
    stopAllExecutionPolling()
    set({ entries: {}, loading: {}, errors: {}, finishingTask: {}, resettingWorkspace: {} })
  },
}))
