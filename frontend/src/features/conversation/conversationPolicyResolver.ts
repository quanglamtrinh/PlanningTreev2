import type { NodeWorkflowView } from '../../api/types'
import type { ComposerAccessMode } from '../session_v2/components/ComposerPane'
import type { ThreadCreationPolicy, TurnExecutionPolicy } from '../session_v2/contracts'
import type { ThreadTab } from './surfaceRouting'

type ConversationPolicyContext = {
  threadTab: ThreadTab
  workflowState: NodeWorkflowView | null | undefined
  projectId: string | null | undefined
  nodeId: string | null | undefined
}

export type ResolveTurnExecutionPolicyInput = ConversationPolicyContext & {
  accessMode: ComposerAccessMode
}

export type ResolveThreadCreationPolicyInput = ConversationPolicyContext

export function resolveTurnExecutionPolicy(
  input: ResolveTurnExecutionPolicyInput,
): TurnExecutionPolicy | undefined {
  if (input.accessMode !== 'full-access') {
    return undefined
  }

  return {
    approvalPolicy: 'never',
    sandboxPolicy: { type: 'dangerFullAccess' },
  }
}

export function resolveThreadCreationPolicy(
  input: ResolveThreadCreationPolicyInput,
): ThreadCreationPolicy | undefined {
  void input
  return undefined
}
