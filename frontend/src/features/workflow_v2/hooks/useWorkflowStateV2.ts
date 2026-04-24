import { useWorkflowStateStoreV2, workflowStateKeyV2 } from '../store/workflowStateStoreV2'

export function useWorkflowStateV2(projectId: string | null | undefined, nodeId: string | null | undefined) {
  const key = projectId && nodeId ? workflowStateKeyV2(projectId, nodeId) : ''
  const workflowState = useWorkflowStateStoreV2((state) => (key ? state.entries[key] : undefined))
  const isLoading = useWorkflowStateStoreV2((state) => (key ? state.loading[key] === true : false))
  const error = useWorkflowStateStoreV2((state) => (key ? state.errors[key] || null : null))
  const loadWorkflowState = useWorkflowStateStoreV2((state) => state.loadWorkflowState)

  return {
    workflowState,
    isLoading,
    error,
    loadWorkflowState,
  }
}
