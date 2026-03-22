import { create } from 'zustand'
import type { DetailState } from '../api/types'
import { api } from '../api/client'

type DetailStateStoreState = {
  /** Keyed by `${projectId}::${nodeId}` */
  entries: Record<string, DetailState>
  loading: Record<string, boolean>
  errors: Record<string, string>

  loadDetailState: (projectId: string, nodeId: string) => Promise<void>
  confirmFrame: (projectId: string, nodeId: string) => Promise<DetailState>
  confirmSpec: (projectId: string, nodeId: string) => Promise<DetailState>
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

  async loadDetailState(projectId: string, nodeId: string) {
    const key = stateKey(projectId, nodeId)
    if (get().loading[key]) return
    set((s) => ({ loading: { ...s.loading, [key]: true }, errors: { ...s.errors, [key]: '' } }))
    try {
      const state = await api.getDetailState(projectId, nodeId)
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
    const state = await api.confirmFrame(projectId, nodeId)
    const key = stateKey(projectId, nodeId)
    set((s) => ({ entries: { ...s.entries, [key]: state } }))
    return state
  },

  async confirmSpec(projectId: string, nodeId: string) {
    const state = await api.confirmSpec(projectId, nodeId)
    const key = stateKey(projectId, nodeId)
    set((s) => ({ entries: { ...s.entries, [key]: state } }))
    return state
  },

  reset() {
    set({ entries: {}, loading: {}, errors: {} })
  },
}))
