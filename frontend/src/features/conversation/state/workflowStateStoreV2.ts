import { create } from 'zustand'
import { api } from '../../../api/client'
import type { NodeWorkflowView } from '../../../api/types'

type WorkflowMutationAction =
  | 'finish_task'
  | 'mark_done_from_execution'
  | 'review_in_audit'
  | 'mark_done_from_audit'
  | 'improve_in_execution'

type WorkflowStateStoreV2State = {
  entries: Record<string, NodeWorkflowView>
  loading: Record<string, boolean>
  errors: Record<string, string>
  activeMutations: Record<string, WorkflowMutationAction | null>

  loadWorkflowState: (projectId: string, nodeId: string) => Promise<NodeWorkflowView>
  finishTask: (projectId: string, nodeId: string) => Promise<NodeWorkflowView>
  markDoneFromExecution: (
    projectId: string,
    nodeId: string,
    expectedWorkspaceHash: string,
  ) => Promise<NodeWorkflowView>
  reviewInAudit: (
    projectId: string,
    nodeId: string,
    expectedWorkspaceHash: string,
  ) => Promise<NodeWorkflowView>
  markDoneFromAudit: (
    projectId: string,
    nodeId: string,
    expectedReviewCommitSha: string,
  ) => Promise<NodeWorkflowView>
  improveInExecution: (
    projectId: string,
    nodeId: string,
    expectedReviewCommitSha: string,
  ) => Promise<NodeWorkflowView>
  reset: () => void
}

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

async function reloadWorkflowState(
  projectId: string,
  nodeId: string,
  set: (
    partial:
      | Partial<WorkflowStateStoreV2State>
      | ((state: WorkflowStateStoreV2State) => Partial<WorkflowStateStoreV2State>),
  ) => void,
): Promise<NodeWorkflowView> {
  const workflowState = await api.getWorkflowStateV2(projectId, nodeId)
  const key = stateKey(projectId, nodeId)
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

async function runWorkflowMutation(
  params: {
    projectId: string
    nodeId: string
    action: WorkflowMutationAction
    mutate: () => Promise<unknown>
  },
  set: (
    partial:
      | Partial<WorkflowStateStoreV2State>
      | ((state: WorkflowStateStoreV2State) => Partial<WorkflowStateStoreV2State>),
  ) => void,
): Promise<NodeWorkflowView> {
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
    await mutate()
    return await reloadWorkflowState(projectId, nodeId, set)
  } catch (error) {
    const message = toErrorMessage(error)
    set((state) => ({
      errors: {
        ...state.errors,
        [key]: message,
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
      return await reloadWorkflowState(projectId, nodeId, set)
    } catch (error) {
      const message = toErrorMessage(error)
      set((state) => ({
        loading: {
          ...state.loading,
          [key]: false,
        },
        errors: {
          ...state.errors,
          [key]: message,
        },
      }))
      throw error
    }
  },

  finishTask(projectId: string, nodeId: string) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'finish_task',
        mutate: () => api.finishTaskWorkflowV2(projectId, nodeId, newIdempotencyKey('finish_task')),
      },
      set,
    )
  },

  markDoneFromExecution(projectId: string, nodeId: string, expectedWorkspaceHash: string) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'mark_done_from_execution',
        mutate: () =>
          api.markDoneFromExecutionV2(
            projectId,
            nodeId,
            newIdempotencyKey('mark_done_from_execution'),
            expectedWorkspaceHash,
          ),
      },
      set,
    )
  },

  reviewInAudit(projectId: string, nodeId: string, expectedWorkspaceHash: string) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'review_in_audit',
        mutate: () =>
          api.reviewInAuditV2(
            projectId,
            nodeId,
            newIdempotencyKey('review_in_audit'),
            expectedWorkspaceHash,
          ),
      },
      set,
    )
  },

  markDoneFromAudit(projectId: string, nodeId: string, expectedReviewCommitSha: string) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'mark_done_from_audit',
        mutate: () =>
          api.markDoneFromAuditV2(
            projectId,
            nodeId,
            newIdempotencyKey('mark_done_from_audit'),
            expectedReviewCommitSha,
          ),
      },
      set,
    )
  },

  improveInExecution(projectId: string, nodeId: string, expectedReviewCommitSha: string) {
    return runWorkflowMutation(
      {
        projectId,
        nodeId,
        action: 'improve_in_execution',
        mutate: () =>
          api.improveInExecutionV2(
            projectId,
            nodeId,
            newIdempotencyKey('improve_in_execution'),
            expectedReviewCommitSha,
          ),
      },
      set,
    )
  },

  reset() {
    set({
      entries: {},
      loading: {},
      errors: {},
      activeMutations: {},
    })
  },
}))
