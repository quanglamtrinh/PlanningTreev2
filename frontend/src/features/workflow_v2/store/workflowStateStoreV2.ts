import { create } from 'zustand'

import {
  acceptAuditV2,
  ensureWorkflowThreadV2,
  getWorkflowStateV2,
  improveExecutionV2,
  markDoneFromExecutionV2,
  startAuditV2,
  startExecutionV2,
  startPackageReviewV2,
  type WorkflowModelPolicyV2,
  type WorkflowMutationResponseV2,
} from '../api/client'
import type { WorkflowStateV2, WorkflowThreadRoleV2 } from '../types'

export type WorkflowMutationActionV2 =
  | 'ensure_thread'
  | 'start_execution'
  | 'complete_execution'
  | 'start_audit'
  | 'improve_execution'
  | 'accept_audit'
  | 'start_package_review'

export type WorkflowStateStoreV2State = {
  entries: Record<string, WorkflowStateV2>
  loading: Record<string, boolean>
  errors: Record<string, string>
  activeMutations: Record<string, WorkflowMutationActionV2 | null>
  loadWorkflowState: (projectId: string, nodeId: string) => Promise<WorkflowStateV2>
  ensureThread: (
    projectId: string,
    nodeId: string,
    role: WorkflowThreadRoleV2,
    options?: WorkflowModelPolicyV2 & { forceRebase?: boolean },
  ) => Promise<WorkflowStateV2>
  startExecution: (
    projectId: string,
    nodeId: string,
    options?: WorkflowModelPolicyV2,
  ) => Promise<WorkflowStateV2>
  completeExecution: (
    projectId: string,
    nodeId: string,
    expectedWorkspaceHash: string,
  ) => Promise<WorkflowStateV2>
  startAudit: (
    projectId: string,
    nodeId: string,
    expectedWorkspaceHash: string,
    options?: WorkflowModelPolicyV2,
  ) => Promise<WorkflowStateV2>
  improveExecution: (
    projectId: string,
    nodeId: string,
    expectedReviewCommitSha: string,
    options?: WorkflowModelPolicyV2,
  ) => Promise<WorkflowStateV2>
  acceptAudit: (
    projectId: string,
    nodeId: string,
    expectedReviewCommitSha: string,
  ) => Promise<WorkflowStateV2>
  startPackageReview: (
    projectId: string,
    nodeId: string,
    options?: WorkflowModelPolicyV2,
  ) => Promise<WorkflowStateV2>
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

function newIdempotencyKey(prefix: string): string {
  const random =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(16).slice(2)}`
  return `${prefix}:${random}`
}

function applyWorkflowState(
  workflowState: WorkflowStateV2,
  set: (
    partial:
      | Partial<WorkflowStateStoreV2State>
      | ((state: WorkflowStateStoreV2State) => Partial<WorkflowStateStoreV2State>),
  ) => void,
): WorkflowStateV2 {
  const key = stateKey(workflowState.projectId, workflowState.nodeId)
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

async function workflowStateFromMutationResponse(
  projectId: string,
  nodeId: string,
  response: WorkflowMutationResponseV2,
  set: (
    partial:
      | Partial<WorkflowStateStoreV2State>
      | ((state: WorkflowStateStoreV2State) => Partial<WorkflowStateStoreV2State>),
  ) => void,
): Promise<WorkflowStateV2> {
  if (response.workflowState) {
    return applyWorkflowState(response.workflowState, set)
  }
  return await requestWorkflowState(projectId, nodeId, set)
}

async function runWorkflowMutation(
  params: {
    projectId: string
    nodeId: string
    action: WorkflowMutationActionV2
    mutate: () => Promise<WorkflowMutationResponseV2>
  },
  set: (
    partial:
      | Partial<WorkflowStateStoreV2State>
      | ((state: WorkflowStateStoreV2State) => Partial<WorkflowStateStoreV2State>),
  ) => void,
): Promise<WorkflowStateV2> {
  const { projectId, nodeId, action, mutate } = params
  const key = stateKey(projectId, nodeId)
  set((state) => ({
    activeMutations: {
      ...state.activeMutations,
      [key]: action,
    },
    errors: {
      ...state.errors,
      [key]: '',
    },
  }))

  try {
    const response = await mutate()
    return await workflowStateFromMutationResponse(projectId, nodeId, response, set)
  } catch (error) {
    set((state) => ({
      errors: {
        ...state.errors,
        [key]: toErrorMessage(error),
      },
    }))
    throw error
  } finally {
    set((state) => ({
      activeMutations: {
        ...state.activeMutations,
        [key]: null,
      },
    }))
  }
}

export const useWorkflowStateStoreV2 = create<WorkflowStateStoreV2State>((set) => ({
  entries: {},
  loading: {},
  errors: {},
  activeMutations: {},

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

  ensureThread(projectId, nodeId, role, options) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'ensure_thread',
        mutate: () =>
          ensureWorkflowThreadV2(projectId, nodeId, role, {
            idempotencyKey: newIdempotencyKey(`ensure_thread:${role}`),
            model: options?.model ?? null,
            modelProvider: options?.modelProvider ?? null,
            forceRebase: options?.forceRebase ?? false,
          }),
      },
      set,
    )
  },

  startExecution(projectId, nodeId, options) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'start_execution',
        mutate: () =>
          startExecutionV2(projectId, nodeId, {
            idempotencyKey: newIdempotencyKey('start_execution'),
            model: options?.model ?? null,
            modelProvider: options?.modelProvider ?? null,
          }),
      },
      set,
    )
  },

  completeExecution(projectId, nodeId, expectedWorkspaceHash) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'complete_execution',
        mutate: () =>
          markDoneFromExecutionV2(projectId, nodeId, {
            idempotencyKey: newIdempotencyKey('complete_execution'),
            expectedWorkspaceHash,
          }),
      },
      set,
    )
  },

  startAudit(projectId, nodeId, expectedWorkspaceHash, options) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'start_audit',
        mutate: () =>
          startAuditV2(projectId, nodeId, {
            idempotencyKey: newIdempotencyKey('start_audit'),
            expectedWorkspaceHash,
            model: options?.model ?? null,
            modelProvider: options?.modelProvider ?? null,
          }),
      },
      set,
    )
  },

  improveExecution(projectId, nodeId, expectedReviewCommitSha, options) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'improve_execution',
        mutate: () =>
          improveExecutionV2(projectId, nodeId, {
            idempotencyKey: newIdempotencyKey('improve_execution'),
            expectedReviewCommitSha,
            model: options?.model ?? null,
            modelProvider: options?.modelProvider ?? null,
          }),
      },
      set,
    )
  },

  acceptAudit(projectId, nodeId, expectedReviewCommitSha) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'accept_audit',
        mutate: () =>
          acceptAuditV2(projectId, nodeId, {
            idempotencyKey: newIdempotencyKey('accept_audit'),
            expectedReviewCommitSha,
          }),
      },
      set,
    )
  },

  startPackageReview(projectId, nodeId, options) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'start_package_review',
        mutate: () =>
          startPackageReviewV2(projectId, nodeId, {
            idempotencyKey: newIdempotencyKey('start_package_review'),
            model: options?.model ?? null,
            modelProvider: options?.modelProvider ?? null,
          }),
      },
      set,
    )
  },

  reset() {
    workflowStateInFlight.clear()
    set({
      entries: {},
      loading: {},
      errors: {},
      activeMutations: {},
    })
  },
}))

export function workflowStateKeyV2(projectId: string, nodeId: string): string {
  return stateKey(projectId, nodeId)
}
