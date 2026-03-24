import { create } from 'zustand'
import type { DetailState } from '../api/types'
import { api } from '../api/client'
import { mergeMockDetailState } from '../dev/mockDetailState'

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
  confirmFrame: (projectId: string, nodeId: string) => Promise<DetailState>
  confirmSpec: (projectId: string, nodeId: string) => Promise<DetailState>
  /** Stub until POST .../finish-task exists */
  finishTask: (projectId: string, nodeId: string) => Promise<void>
  /** Stub until POST .../git/init exists */
  initGit: (projectId: string) => Promise<void>
  /** Stub until POST .../reset-workspace exists */
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
    } catch (error) {
      set((s) => ({
        loading: { ...s.loading, [key]: false },
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
    set((s) => ({ finishingTask: { ...s.finishingTask, [key]: true } }))
    try {
      // await api.finishTask(projectId, nodeId) when API exists
      await Promise.resolve()
    } finally {
      set((s) => ({ finishingTask: { ...s.finishingTask, [key]: false } }))
    }
  },

  async initGit(projectId: string) {
    void projectId
    // await api.initGit(projectId) when API exists
    await Promise.resolve()
  },

  async resetWorkspace(projectId: string, nodeId: string, target: 'initial' | 'head') {
    const key = stateKey(projectId, nodeId)
    set((s) => ({ resettingWorkspace: { ...s.resettingWorkspace, [key]: true } }))
    try {
      void target
      // await api.resetWorkspace(projectId, nodeId, { target }) when API exists
      await Promise.resolve()
    } finally {
      set((s) => ({ resettingWorkspace: { ...s.resettingWorkspace, [key]: false } }))
    }
  },

  reset() {
    set({ entries: {}, loading: {}, errors: {}, finishingTask: {}, resettingWorkspace: {} })
  },
}))
