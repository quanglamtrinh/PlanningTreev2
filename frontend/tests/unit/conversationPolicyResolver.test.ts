import { describe, expect, it } from 'vitest'

import {
  resolveTurnSessionConfig,
  resolveThreadCreationPolicy,
  resolveTurnExecutionPolicy,
} from '../../src/features/conversation/conversationPolicyResolver'

describe('conversationPolicyResolver', () => {
  it('maps full-access composer intent to native execution policy', () => {
    expect(
      resolveTurnExecutionPolicy({
        threadTab: 'execution',
        accessMode: 'full-access',
        workflowState: null,
        projectId: 'project-1',
        nodeId: 'node-1',
      }),
    ).toEqual({
      model: undefined,
      cwd: undefined,
      approvalPolicy: 'never',
      approvalsReviewer: undefined,
      sandboxPolicy: { type: 'dangerFullAccess' },
      personality: undefined,
      effort: null,
      summary: null,
      serviceTier: undefined,
      outputSchema: undefined,
    })
  })

  it('merges composer session config before mapping turn policy', () => {
    expect(
      resolveTurnExecutionPolicy({
        threadTab: 'ask',
        accessMode: 'default-permissions',
        workflowState: null,
        projectId: 'project-1',
        nodeId: 'node-1',
        sessionConfig: {
          model: 'gpt-5.4',
          cwd: 'C:/repo',
          reasoning: { effort: 'xhigh', summary: null },
          serviceTier: 'priority',
          config: {
            composer: {
              workMode: 'locally',
              streamMode: 'streaming',
            },
          },
        },
      }),
    ).toEqual({
      model: 'gpt-5.4',
      cwd: 'C:/repo',
      approvalPolicy: undefined,
      approvalsReviewer: undefined,
      sandboxPolicy: undefined,
      personality: undefined,
      effort: 'xhigh',
      summary: null,
      serviceTier: 'priority',
      outputSchema: undefined,
    })
  })

  it('keeps full-access decision as a session config overlay', () => {
    expect(
      resolveTurnSessionConfig({
        threadTab: 'execution',
        accessMode: 'full-access',
        workflowState: null,
        projectId: 'project-1',
        nodeId: 'node-1',
        sessionConfig: {
          model: 'gpt-5.4',
          reasoning: { effort: 'high', summary: null },
        },
      }),
    ).toEqual({
      model: 'gpt-5.4',
      reasoning: { effort: 'high', summary: null },
      approvalPolicy: 'never',
      sandboxPolicy: { type: 'dangerFullAccess' },
    })
  })

  it('leaves default-permissions on backend defaults', () => {
    expect(
      resolveTurnExecutionPolicy({
        threadTab: 'ask',
        accessMode: 'default-permissions',
        workflowState: null,
        projectId: 'project-1',
        nodeId: 'node-1',
      }),
    ).toBeUndefined()
  })

  it('leaves thread creation policy unset by default', () => {
    expect(
      resolveThreadCreationPolicy({
        threadTab: 'audit',
        workflowState: null,
        projectId: 'project-1',
        nodeId: 'node-1',
      }),
    ).toBeUndefined()
  })

  it('maps thread session config when supplied', () => {
    expect(
      resolveThreadCreationPolicy({
        threadTab: 'audit',
        workflowState: null,
        projectId: 'project-1',
        nodeId: 'node-1',
        sessionConfig: {
          model: 'gpt-5.4',
          modelProvider: 'openai',
          cwd: 'C:/repo',
          ephemeral: true,
        },
      }),
    ).toEqual({
      model: 'gpt-5.4',
      modelProvider: 'openai',
      cwd: 'C:/repo',
      approvalPolicy: undefined,
      approvalsReviewer: undefined,
      sandbox: undefined,
      personality: undefined,
      serviceTier: undefined,
      baseInstructions: undefined,
      developerInstructions: undefined,
      config: undefined,
      ephemeral: true,
    })
  })
})
