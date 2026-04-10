import { describe, expect, it } from 'vitest'

import type { ThreadSnapshotV3 } from '../../src/api/types'
import {
  buildToolGroupsV3,
  deriveVisibleMessageStateV3,
} from '../../src/features/conversation/components/v3/messagesV3.utils'

function makeSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
  return {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadId: 'thread-1',
    threadRole: 'execution',
    lane: 'execution',
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-04-01T00:00:00Z',
    updatedAt: '2026-04-01T00:00:00Z',
    items: [],
    uiSignals: {
      planReady: {
        planItemId: null,
        revision: null,
        ready: false,
        failed: false,
      },
      activeUserInputRequests: [],
    },
    ...overrides,
  }
}

describe('messagesV3.utils', () => {
  it('deriveVisibleMessageStateV3 filters empty message/reasoning content', () => {
    const snapshot = makeSnapshot({
      items: [
        {
          id: 'msg-empty',
          kind: 'message',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 1,
          createdAt: '2026-04-01T00:00:01Z',
          updatedAt: '2026-04-01T00:00:01Z',
          status: 'in_progress',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          role: 'assistant',
          text: '   ',
          format: 'markdown',
        },
        {
          id: 'reason-empty',
          kind: 'reasoning',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 2,
          createdAt: '2026-04-01T00:00:02Z',
          updatedAt: '2026-04-01T00:00:02Z',
          status: 'in_progress',
          source: 'upstream',
          tone: 'muted',
          metadata: {},
          summaryText: '   ',
          detailText: null,
        },
        {
          id: 'msg-1',
          kind: 'message',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 3,
          createdAt: '2026-04-01T00:00:03Z',
          updatedAt: '2026-04-01T00:00:03Z',
          status: 'completed',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          role: 'assistant',
          text: 'Visible text',
          format: 'markdown',
        },
      ],
    })

    const state = deriveVisibleMessageStateV3(snapshot)

    expect(state.visibleItems.map((item) => item.id)).toEqual(['msg-1'])
  })

  it('buildToolGroupsV3 groups consecutive tool stream segments', () => {
    const items = makeSnapshot({
      items: [
        {
          id: 'tool-1',
          kind: 'tool',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 1,
          createdAt: '2026-04-01T00:00:01Z',
          updatedAt: '2026-04-01T00:00:01Z',
          status: 'in_progress',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          toolType: 'commandExecution',
          title: 'Run tests',
          toolName: 'powershell',
          callId: 'call-1',
          argumentsText: 'npm test',
          outputText: '',
          outputFiles: [],
          exitCode: null,
        },
        {
          id: 'review-1',
          kind: 'review',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 2,
          createdAt: '2026-04-01T00:00:02Z',
          updatedAt: '2026-04-01T00:00:02Z',
          status: 'in_progress',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          title: 'Plan',
          text: 'Draft plan',
          disposition: null,
        },
        {
          id: 'tool-2',
          kind: 'tool',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 3,
          createdAt: '2026-04-01T00:00:03Z',
          updatedAt: '2026-04-01T00:00:03Z',
          status: 'completed',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          toolType: 'fileChange',
          title: 'Apply patch',
          toolName: 'apply_patch',
          callId: 'call-2',
          argumentsText: null,
          outputText: '',
          outputFiles: [],
          exitCode: 0,
        },
        {
          id: 'msg-1',
          kind: 'message',
          threadId: 'thread-1',
          turnId: 'turn-1',
          sequence: 4,
          createdAt: '2026-04-01T00:00:04Z',
          updatedAt: '2026-04-01T00:00:04Z',
          status: 'completed',
          source: 'upstream',
          tone: 'neutral',
          metadata: {},
          role: 'assistant',
          text: 'Done',
          format: 'markdown',
        },
      ],
    }).items

    const grouped = buildToolGroupsV3(items)
    expect(grouped).toHaveLength(2)
    expect(grouped[0].kind).toBe('toolGroup')
    if (grouped[0].kind === 'toolGroup') {
      expect(grouped[0].group.toolCount).toBe(2)
      expect(grouped[0].group.supportingItemCount).toBe(1)
    }
    expect(grouped[1]).toEqual({
      kind: 'item',
      item: items[3],
    })
  })
})
