import { create } from 'zustand'

import { getWorkflowStateV2 } from '../api/client'
import type { WorkflowStateV2 } from '../types'

type WorkflowStateStoreV2State = {
  entries: Record<string, WorkflowStateV2>
  loading: Record<string, boolean>
  errors: Record<string, string>
  loadWorkflowState: (projectId: string, nodeId: string) => Promise<WorkflowStateV2>
  reset: () => void
}

const workflowStateInFlight = new Map<string, Promise<WorkflowStateV2>>()

function stateKey(projectId: string, nodeId: string): string {
  return `${projectId}::${nodeId}`
}

function toErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message
  }
  return String(error)
}

async function requestWorkflowState(
  projectId: string,
  nodeId: string,
  set: (
    partial:
      | Partial<WorkflowStateStoreV2State>
      | ((state: WorkflowStateStoreV2State) => Partial<WorkflowStateStoreV2State>),
  ) => void,
): Promise<WorkflowStateV2> {
  const key = stateKey(projectId, nodeId)
  const existing = workflowStateInFlight.get(key)
  if (existing) {
    return existing
  }
  const request = getWorkflowStateV2(projectId, nodeId)
    .then((workflowState) => {
      set((state) => ({
        entries: {
          ...state.entries,
          [key]: workflowState,
        },
        loading: {
          ...state.loading,
          [key]: false,
        },
        errors: {
          ...state.errors,
          [key]: '',
        },
      }))
      return workflowState
    })
    .finally(() => {
      workflowStateInFlight.delete(key)
    })
  workflowStateInFlight.set(key, request)
  return request
}

export const useWorkflowStateStoreV2 = create<WorkflowStateStoreV2State>((set) => ({
  entries: {},
  loading: {},
  errors: {},

  async loadWorkflowState(projectId: string, nodeId: string) {
    const key = stateKey(projectId, nodeId)
    if (workflowStateInFlight.has(key)) {
      return await (workflowStateInFlight.get(key) as Promise<WorkflowStateV2>)
    }

    set((state) => ({
      loading: {
        ...state.loading,
        [key]: true,
      },
      errors: {
        ...state.errors,
        [key]: '',
      },
    }))

    try {
      return await requestWorkflowState(projectId, nodeId, set)
    } catch (error) {
      set((state) => ({
        loading: {
          ...state.loading,
          [key]: false,
        },
        errors: {
          ...state.errors,
          [key]: toErrorMessage(error),
        },
      }))
      throw error
    }
  },

  reset() {
    workflowStateInFlight.clear()
    set({
      entries: {},
      loading: {},
      errors: {},
    })
  },
}))

export function workflowStateKeyV2(projectId: string, nodeId: string): string {
  return stateKey(projectId, nodeId)
}
