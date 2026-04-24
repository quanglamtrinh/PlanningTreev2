import type { NodeWorkflowView } from '../../api/types'
import type { ComposerAccessMode } from '../session_v2/components/ComposerPane'
import {
  toThreadCreationPolicy,
  toTurnExecutionPolicy,
  type SessionConfig,
  type ThreadCreationPolicy,
  type TurnExecutionPolicy,
} from '../session_v2/contracts'
import type { ThreadTab } from './surfaceRouting'

type ConversationPolicyContext = {
  threadTab: ThreadTab
  workflowState: NodeWorkflowView | null | undefined
  projectId: string | null | undefined
  nodeId: string | null | undefined
}

export type ResolveTurnExecutionPolicyInput = ConversationPolicyContext & {
  accessMode: ComposerAccessMode
  sessionConfig?: SessionConfig | null
}

export type ResolveThreadCreationPolicyInput = ConversationPolicyContext & {
  sessionConfig?: SessionConfig | null
}

export function resolveTurnSessionConfig(
  input: ResolveTurnExecutionPolicyInput,
): SessionConfig | undefined {
  const baseConfig = input.sessionConfig ? { ...input.sessionConfig } : null
  if (input.accessMode !== 'full-access') {
    return baseConfig ?? undefined
  }

  return {
    ...(baseConfig ?? {}),
    approvalPolicy: 'never',
    sandboxPolicy: { type: 'dangerFullAccess' },
  }
}

export function resolveTurnExecutionPolicy(
  input: ResolveTurnExecutionPolicyInput,
): TurnExecutionPolicy | undefined {
  const config = resolveTurnSessionConfig(input)
  return config ? toTurnExecutionPolicy(config) : undefined
}

export function resolveThreadCreationPolicy(
  input: ResolveThreadCreationPolicyInput,
): ThreadCreationPolicy | undefined {
  return input.sessionConfig ? toThreadCreationPolicy(input.sessionConfig) : undefined
}
