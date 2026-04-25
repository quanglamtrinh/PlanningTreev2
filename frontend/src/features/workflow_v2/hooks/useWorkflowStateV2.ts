import { useWorkflowStateStoreV2, workflowStateKeyV2 } from '../store/workflowStateStoreV2'

export function useWorkflowStateV2(projectId: string | null | undefined, nodeId: string | null | undefined) {
  const key = projectId && nodeId ? workflowStateKeyV2(projectId, nodeId) : ''
  const workflowState = useWorkflowStateStoreV2((state) => (key ? state.entries[key] : undefined))
  const isLoading = useWorkflowStateStoreV2((state) => (key ? state.loading[key] === true : false))
  const error = useWorkflowStateStoreV2((state) => (key ? state.errors[key] || null : null))
  const activeMutation = useWorkflowStateStoreV2((state) =>
    key ? state.activeMutations[key] ?? null : null,
  )
  const loadWorkflowState = useWorkflowStateStoreV2((state) => state.loadWorkflowState)
  const ensureThread = useWorkflowStateStoreV2((state) => state.ensureThread)
  const startExecution = useWorkflowStateStoreV2((state) => state.startExecution)
  const completeExecution = useWorkflowStateStoreV2((state) => state.completeExecution)
  const startAudit = useWorkflowStateStoreV2((state) => state.startAudit)
  const improveExecution = useWorkflowStateStoreV2((state) => state.improveExecution)
  const acceptAudit = useWorkflowStateStoreV2((state) => state.acceptAudit)
  const startPackageReview = useWorkflowStateStoreV2((state) => state.startPackageReview)

  return {
    workflowState,
    isLoading,
    error,
    activeMutation,
    loadWorkflowState,
    ensureThread,
    startExecution,
    completeExecution,
    startAudit,
    improveExecution,
    acceptAudit,
    startPackageReview,
  }
}
