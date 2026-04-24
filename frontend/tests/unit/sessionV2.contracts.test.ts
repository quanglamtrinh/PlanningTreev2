import { describe, expect, it } from 'vitest'

import {
  toThreadCreationPolicy,
  toTurnExecutionPolicy,
  type SessionConfig,
} from '../../src/features/session_v2/contracts'

describe('session V2 contracts', () => {
  it('maps SessionConfig to thread creation policy', () => {
    const config: SessionConfig = {
      model: 'gpt-5.4',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      approvalPolicy: 'onRequest',
      approvalsReviewer: 'reviewer-1',
      sandbox: { type: 'workspaceWrite' },
      sandboxPolicy: { type: 'dangerFullAccess' },
      reasoning: { effort: 'xhigh', summary: 'auto' },
      personality: 'concise',
      serviceTier: 'priority',
      outputSchema: { type: 'object' },
      baseInstructions: 'base',
      developerInstructions: 'developer',
      config: { composer: { streamMode: 'streaming' } },
      ephemeral: true,
    }

    expect(toThreadCreationPolicy(config)).toEqual({
      model: 'gpt-5.4',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      approvalPolicy: 'onRequest',
      approvalsReviewer: 'reviewer-1',
      sandbox: { type: 'workspaceWrite' },
      personality: 'concise',
      serviceTier: 'priority',
      baseInstructions: 'base',
      developerInstructions: 'developer',
      config: { composer: { streamMode: 'streaming' } },
      ephemeral: true,
    })
  })

  it('maps SessionConfig to turn execution policy', () => {
    const config: SessionConfig = {
      model: 'gpt-5.4',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      approvalPolicy: 'never',
      approvalsReviewer: 'reviewer-1',
      sandbox: { type: 'workspaceWrite' },
      sandboxPolicy: { type: 'dangerFullAccess' },
      reasoning: { effort: 'xhigh', summary: { type: 'auto' } },
      personality: 'concise',
      serviceTier: 'priority',
      outputSchema: { type: 'object' },
      baseInstructions: 'base',
      developerInstructions: 'developer',
      config: { composer: { streamMode: 'streaming' } },
      ephemeral: true,
    }

    expect(toTurnExecutionPolicy(config)).toEqual({
      model: 'gpt-5.4',
      cwd: 'C:/repo',
      approvalPolicy: 'never',
      approvalsReviewer: 'reviewer-1',
      sandboxPolicy: { type: 'dangerFullAccess' },
      personality: 'concise',
      effort: 'xhigh',
      summary: { type: 'auto' },
      serviceTier: 'priority',
      outputSchema: { type: 'object' },
    })
  })
})
