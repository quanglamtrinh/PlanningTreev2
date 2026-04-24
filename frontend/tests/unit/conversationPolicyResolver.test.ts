import { describe, expect, it } from 'vitest'

import {
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
})
