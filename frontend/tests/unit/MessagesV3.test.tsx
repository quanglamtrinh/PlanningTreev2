import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ThreadSnapshotV3 } from '../../src/api/types'
import { MessagesV3 } from '../../src/features/conversation/components/v3/MessagesV3'

function makeSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
  return {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadId: 'thread-1',
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

describe('MessagesV3', () => {
  it('shows plan-ready card, dispatches actions, and persists dismissal key', async () => {
    vi.useFakeTimers()
    try {
      const onPlanAction = vi.fn().mockResolvedValue(undefined)
      const onResolveUserInput = vi.fn().mockResolvedValue(undefined)

      render(
        <MessagesV3
          snapshot={makeSnapshot({
            items: [
              {
                id: 'plan-1',
                kind: 'review',
                threadId: 'thread-1',
                turnId: 'turn-1',
                sequence: 3,
                createdAt: '2026-04-01T00:00:01Z',
                updatedAt: '2026-04-01T00:00:01Z',
                status: 'completed',
                source: 'upstream',
                tone: 'neutral',
                metadata: { v2Kind: 'plan' },
                title: 'Plan',
                text: 'Plan content',
                disposition: null,
              },
            ],
            uiSignals: {
              planReady: {
                planItemId: 'plan-1',
                revision: 3,
                ready: true,
                failed: false,
              },
              activeUserInputRequests: [],
            },
          })}
          isLoading={false}
          isSending={false}
          onResolveUserInput={onResolveUserInput}
          onPlanAction={onPlanAction}
        />,
      )

      expect(screen.getByTestId('conversation-v3-plan-ready-card')).toBeInTheDocument()

      fireEvent.click(screen.getByRole('button', { name: 'Implement this plan' }))
      expect(onPlanAction).toHaveBeenCalledWith('implement_plan', 'plan-1', 3)

      fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
      expect(screen.queryByTestId('conversation-v3-plan-ready-card')).not.toBeInTheDocument()

      vi.advanceTimersByTime(250)
      const stored = window.localStorage.getItem('ptm.uiux.v3.thread.thread-1.viewState')
      expect(stored).toBeTruthy()
      const payload = JSON.parse(String(stored)) as { dismissedPlanReadyKeys: string[] }
      expect(payload.dismissedPlanReadyKeys).toContain('thread-1:plan-1:3')
    } finally {
      vi.useRealTimers()
    }
  })

  it('suppresses plan-ready card when blocked by pending user-input or superseded by user message', () => {
    const onResolveUserInput = vi.fn().mockResolvedValue(undefined)

    const { rerender } = render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'plan-1',
              kind: 'review',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 3,
              createdAt: '2026-04-01T00:00:01Z',
              updatedAt: '2026-04-01T00:00:01Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: { v2Kind: 'plan' },
              title: 'Plan',
              text: 'Plan content',
              disposition: null,
            },
          ],
          uiSignals: {
            planReady: {
              planItemId: 'plan-1',
              revision: 3,
              ready: true,
              failed: false,
            },
            activeUserInputRequests: [
              {
                requestId: 'req-1',
                itemId: 'input-1',
                threadId: 'thread-1',
                turnId: 'turn-1',
                status: 'requested',
                createdAt: '2026-04-01T00:00:02Z',
                submittedAt: null,
                resolvedAt: null,
                answers: [],
              },
            ],
          },
        })}
        isLoading={false}
        onResolveUserInput={onResolveUserInput}
      />,
    )

    expect(screen.queryByTestId('conversation-v3-plan-ready-card')).not.toBeInTheDocument()

    rerender(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'plan-1',
              kind: 'review',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 3,
              createdAt: '2026-04-01T00:00:01Z',
              updatedAt: '2026-04-01T00:00:01Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: { v2Kind: 'plan' },
              title: 'Plan',
              text: 'Plan content',
              disposition: null,
            },
            {
              id: 'msg-user-1',
              kind: 'message',
              threadId: 'thread-1',
              turnId: 'turn-2',
              sequence: 4,
              createdAt: '2026-04-01T00:00:03Z',
              updatedAt: '2026-04-01T00:00:03Z',
              status: 'completed',
              source: 'local',
              tone: 'neutral',
              metadata: {},
              role: 'user',
              text: 'Superseding message',
              format: 'markdown',
            },
          ],
          uiSignals: {
            planReady: {
              planItemId: 'plan-1',
              revision: 3,
              ready: true,
              failed: false,
            },
            activeUserInputRequests: [],
          },
        })}
        isLoading={false}
        onResolveUserInput={onResolveUserInput}
      />,
    )

    expect(screen.queryByTestId('conversation-v3-plan-ready-card')).not.toBeInTheDocument()
  })

  it('renders pending user-input as dedicated card and answered user-input as compact inline row', () => {
    const onResolveUserInput = vi.fn().mockResolvedValue(undefined)
    const userInputItem = {
      id: 'input-1',
      kind: 'userInput' as const,
      threadId: 'thread-1',
      turnId: 'turn-1',
      sequence: 5,
      createdAt: '2026-04-01T00:00:05Z',
      updatedAt: '2026-04-01T00:00:05Z',
      status: 'requested' as const,
      source: 'upstream' as const,
      tone: 'info' as const,
      metadata: {},
      requestId: 'req-1',
      title: 'Need input',
      questions: [],
      answers: [],
      requestedAt: '2026-04-01T00:00:05Z',
      resolvedAt: null,
    }

    const { rerender } = render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [userInputItem],
          uiSignals: {
            planReady: {
              planItemId: null,
              revision: null,
              ready: false,
              failed: false,
            },
            activeUserInputRequests: [
              {
                requestId: 'req-1',
                itemId: 'input-1',
                threadId: 'thread-1',
                turnId: 'turn-1',
                status: 'requested',
                createdAt: '2026-04-01T00:00:05Z',
                submittedAt: null,
                resolvedAt: null,
                answers: [],
              },
            ],
          },
        })}
        isLoading={false}
        onResolveUserInput={onResolveUserInput}
      />,
    )

    expect(screen.getByTestId('conversation-v3-pending-user-input-req-1')).toBeInTheDocument()
    expect(screen.queryByTestId('conversation-v3-item-userInput-inline')).not.toBeInTheDocument()

    rerender(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              ...userInputItem,
              status: 'answered',
              answers: [{ questionId: 'q1', value: 'yes', label: 'Yes' }],
              resolvedAt: '2026-04-01T00:00:06Z',
            },
          ],
          uiSignals: {
            planReady: {
              planItemId: null,
              revision: null,
              ready: false,
              failed: false,
            },
            activeUserInputRequests: [
              {
                requestId: 'req-1',
                itemId: 'input-1',
                threadId: 'thread-1',
                turnId: 'turn-1',
                status: 'answered',
                createdAt: '2026-04-01T00:00:05Z',
                submittedAt: '2026-04-01T00:00:05Z',
                resolvedAt: '2026-04-01T00:00:06Z',
                answers: [{ questionId: 'q1', value: 'yes', label: 'Yes' }],
              },
            ],
          },
        })}
        isLoading={false}
        onResolveUserInput={onResolveUserInput}
      />,
    )

    expect(screen.queryByTestId('conversation-v3-pending-user-input-req-1')).not.toBeInTheDocument()
    expect(screen.getByTestId('conversation-v3-item-userInput-inline')).toBeInTheDocument()
  })

  it('hydrates and prunes persisted view-state by current snapshot content', () => {
    vi.useFakeTimers()
    try {
      window.localStorage.setItem(
        'ptm.uiux.v3.thread.thread-1.viewState',
        JSON.stringify({
          schemaVersion: 1,
          expandedItemIds: ['tool-1', 'stale-item'],
          collapsedToolGroupIds: ['stale-group'],
          dismissedPlanReadyKeys: ['thread-1:plan-1:1', 'stale-key'],
          updatedAt: '2026-04-01T00:00:00Z',
        }),
      )

      render(
        <MessagesV3
          snapshot={makeSnapshot({
            items: [
              {
                id: 'tool-1',
                kind: 'tool',
                threadId: 'thread-1',
                turnId: 'turn-1',
                sequence: 1,
                createdAt: '2026-04-01T00:00:01Z',
                updatedAt: '2026-04-01T00:00:01Z',
                status: 'completed',
                source: 'upstream',
                tone: 'neutral',
                metadata: {},
                toolType: 'commandExecution',
                title: 'Run tests',
                toolName: 'powershell',
                callId: 'call-1',
                argumentsText: 'npm test',
                outputText: 'line\n'.repeat(20),
                outputFiles: [],
                exitCode: 0,
              },
              {
                id: 'plan-1',
                kind: 'review',
                threadId: 'thread-1',
                turnId: 'turn-1',
                sequence: 1,
                createdAt: '2026-04-01T00:00:01Z',
                updatedAt: '2026-04-01T00:00:01Z',
                status: 'completed',
                source: 'upstream',
                tone: 'neutral',
                metadata: { v2Kind: 'plan' },
                title: 'Plan',
                text: 'Plan content',
                disposition: null,
              },
            ],
            uiSignals: {
              planReady: {
                planItemId: 'plan-1',
                revision: 1,
                ready: true,
                failed: false,
              },
              activeUserInputRequests: [],
            },
          })}
          isLoading={false}
          onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
        />,
      )

      vi.advanceTimersByTime(250)
      const stored = window.localStorage.getItem('ptm.uiux.v3.thread.thread-1.viewState')
      expect(stored).toBeTruthy()
      const payload = JSON.parse(String(stored)) as {
        expandedItemIds: string[]
        collapsedToolGroupIds: string[]
        dismissedPlanReadyKeys: string[]
      }
      expect(payload.expandedItemIds).toContain('tool-1')
      expect(payload.expandedItemIds).not.toContain('stale-item')
      expect(payload.collapsedToolGroupIds).toEqual([])
      expect(payload.dismissedPlanReadyKeys).toEqual(['thread-1:plan-1:1'])
    } finally {
      vi.useRealTimers()
    }
  })
})
