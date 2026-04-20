import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ThreadSnapshotV3 } from '../../src/api/types'
import { MessagesV3 } from '../../src/features/conversation/components/v3/MessagesV3'
import { useThreadByIdStoreV3 } from '../../src/features/conversation/state/threadByIdStoreV3'

function makeSnapshot(overrides: Partial<ThreadSnapshotV3> = {}): ThreadSnapshotV3 {
  const snapshot: ThreadSnapshotV3 = {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadId: 'thread-1',
    threadRole: 'execution',
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
  return snapshot
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

  it('keeps V3 stream/pending/plan-ready structural zones stable', () => {
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
            {
              id: 'input-1',
              kind: 'userInput',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 5,
              createdAt: '2026-04-01T00:00:05Z',
              updatedAt: '2026-04-01T00:00:05Z',
              status: 'requested',
              source: 'upstream',
              tone: 'info',
              metadata: {},
              requestId: 'req-1',
              title: 'Need input',
              questions: [],
              answers: [],
              requestedAt: '2026-04-01T00:00:05Z',
              resolvedAt: null,
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

    expect(screen.getByTestId('messages-v3-stream-stack')).toBeInTheDocument()
    expect(screen.getByTestId('messages-v3-pending-stack')).toBeInTheDocument()
    expect(screen.queryByTestId('messages-v3-plan-ready-zone')).not.toBeInTheDocument()

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

    expect(screen.getByTestId('messages-v3-stream-stack')).toBeInTheDocument()
    expect(screen.queryByTestId('messages-v3-pending-stack')).not.toBeInTheDocument()
    expect(screen.getByTestId('messages-v3-plan-ready-zone')).toBeInTheDocument()
  })

  it('keeps commandExecution tools as command cards even when outputFiles are present', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'tool-edit-1',
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
              title: 'apply_patch',
              toolName: 'apply_patch',
              callId: 'call-1',
              argumentsText: '*** Begin Patch',
              outputText: 'Updated 1 file',
              outputFiles: [
                {
                  path: 'src/app.ts',
                  changeType: 'updated',
                  summary: 'Refine UI rendering',
                },
              ],
              exitCode: 0,
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const toolRow = screen.getByTestId('conversation-v3-item-tool')
    expect(toolRow).toHaveTextContent('Begin Patch')
    expect(screen.queryByLabelText('Copy diff')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Expand command details' }))
    expect(screen.getByTestId('conversation-v3-tool-output-tool-edit-1')).toBeInTheDocument()
    expect(toolRow).toHaveTextContent('app.ts')
  })

  it('renders execution diff rows from canonical changes even when files.patchText is empty', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'diff-1',
              kind: 'diff',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 2,
              createdAt: '2026-04-01T00:00:02Z',
              updatedAt: '2026-04-01T00:00:02Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {
                semanticKind: 'fileChange',
                v2Kind: 'tool',
              },
              title: 'File changes',
              summaryText: null,
              changes: [
                {
                  path: 'src/app.ts',
                  kind: 'modify',
                  summary: null,
                  diff: ['diff --git a/src/app.ts b/src/app.ts', '@@ -1 +1 @@', '-const a = 1', '+const a = 2'].join(
                    '\n',
                  ),
                },
              ],
              files: [
                {
                  path: 'src/app.ts',
                  changeType: 'updated',
                  summary: null,
                  patchText: null,
                },
              ],
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const diffRow = screen.getByTestId('conversation-v3-item-diff')
    expect(diffRow).toHaveTextContent('+1')
    expect(diffRow).toHaveTextContent('-1')
    fireEvent.click(screen.getByRole('button', { name: 'Expand diff' }))
    expect(diffRow).toHaveTextContent(/const\s+a\s*=\s*2/)
  })

  it('renders audit diff rows with file-change semantic through the same file-change renderer', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          threadRole: 'audit',
          items: [
            {
              id: 'audit-diff-1',
              kind: 'diff',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 2,
              createdAt: '2026-04-01T00:00:02Z',
              updatedAt: '2026-04-01T00:00:02Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {
                semanticKind: 'fileChange',
                v2Kind: 'tool',
              },
              title: 'File changes',
              summaryText: null,
              changes: [
                {
                  path: 'src/audit.ts',
                  kind: 'modify',
                  summary: null,
                  diff: ['diff --git a/src/audit.ts b/src/audit.ts', '@@ -1 +1 @@', '-old', '+new'].join(
                    '\n',
                  ),
                },
              ],
              files: [
                {
                  path: 'src/audit.ts',
                  changeType: 'updated',
                  summary: null,
                  patchText: null,
                },
              ],
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const diffRow = screen.getByTestId('conversation-v3-item-diff')
    expect(diffRow).toHaveTextContent('+1')
    expect(diffRow).toHaveTextContent('-1')
    fireEvent.click(screen.getByRole('button', { name: 'Expand diff' }))
    expect(diffRow).toHaveTextContent(/new/)
  })

  it('falls back to files.patchText in audit thread when canonical changes are absent', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          threadRole: 'audit',
          items: [
            {
              id: 'audit-diff-legacy-1',
              kind: 'diff',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 2,
              createdAt: '2026-04-01T00:00:02Z',
              updatedAt: '2026-04-01T00:00:02Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {
                semanticKind: 'fileChange',
                v2Kind: 'tool',
              },
              title: 'File changes',
              summaryText: null,
              changes: [],
              files: [
                {
                  path: 'src/legacy.ts',
                  changeType: 'updated',
                  summary: null,
                  patchText: ['diff --git a/src/legacy.ts b/src/legacy.ts', '@@ -1 +1 @@', '-old', '+new'].join(
                    '\n',
                  ),
                },
              ],
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const diffRow = screen.getByTestId('conversation-v3-item-diff')
    expect(diffRow).toHaveTextContent('+1')
    expect(diffRow).toHaveTextContent('-1')
    fireEvent.click(screen.getByRole('button', { name: 'Expand diff' }))
    expect(diffRow).toHaveTextContent(/new/)
  })

  it('keeps non-fileChange diff semantics on the generic diff card', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          threadRole: 'audit',
          items: [
            {
              id: 'diff-generic-1',
              kind: 'diff',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 2,
              createdAt: '2026-04-01T00:00:02Z',
              updatedAt: '2026-04-01T00:00:02Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {
                semanticKind: 'workflowReviewDiff',
                v2Kind: 'message',
              },
              title: 'Diff Summary',
              summaryText: 'Review diff only',
              changes: [],
              files: [{ path: 'src/audit.ts', changeType: 'updated', summary: 'metadata-only', patchText: null }],
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const diffRow = screen.getByTestId('conversation-v3-item-diff')
    expect(diffRow).toHaveTextContent('Diff')
    expect(diffRow).toHaveTextContent('Diff Summary')
    expect(diffRow).toHaveTextContent('metadata-only')
    expect(screen.queryByLabelText('Copy diff')).not.toBeInTheDocument()
  })

  it('does not synthesize +0/-0 stats when only path metadata is available', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'diff-path-only-1',
              kind: 'diff',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 2,
              createdAt: '2026-04-01T00:00:02Z',
              updatedAt: '2026-04-01T00:00:02Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {
                semanticKind: 'fileChange',
                v2Kind: 'tool',
              },
              title: 'File changes',
              summaryText: null,
              changes: [{ path: 'src/path-only.ts', kind: 'modify', summary: null, diff: null }],
              files: [{ path: 'src/path-only.ts', changeType: 'updated', summary: null, patchText: null }],
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const diffRow = screen.getByTestId('conversation-v3-item-diff')
    expect(diffRow).not.toHaveTextContent('+0')
    expect(diffRow).not.toHaveTextContent('-0')
    fireEvent.click(screen.getByRole('button', { name: 'Expand diff' }))
    expect(diffRow).toHaveTextContent('path-only.ts')
  })

  it('does not emit file-change render loop or malformed SVG path errors', () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      render(
        <MessagesV3
          snapshot={makeSnapshot({
            threadRole: 'audit',
            items: [
              {
                id: 'diff-regression-1',
                kind: 'diff',
                threadId: 'thread-1',
                turnId: 'turn-1',
                sequence: 3,
                createdAt: '2026-04-01T00:00:03Z',
                updatedAt: '2026-04-01T00:00:03Z',
                status: 'completed',
                source: 'upstream',
                tone: 'neutral',
                metadata: {
                  semanticKind: 'fileChange',
                  v2Kind: 'tool',
                },
                title: 'File changes',
                summaryText: null,
                changes: [
                  {
                    path: 'src/a.ts',
                    kind: 'modify',
                    summary: null,
                    diff: ['diff --git a/src/a.ts b/src/a.ts', '@@ -1 +1 @@', '-a', '+aa'].join('\n'),
                  },
                  {
                    path: 'src/b.ts',
                    kind: 'modify',
                    summary: null,
                    diff: ['diff --git a/src/b.ts b/src/b.ts', '@@ -1 +1 @@', '-b', '+bb'].join('\n'),
                  },
                ],
                files: [
                  { path: 'src/a.ts', changeType: 'updated', summary: null, patchText: null },
                  { path: 'src/b.ts', changeType: 'updated', summary: null, patchText: null },
                ],
              },
            ],
          })}
          isLoading={false}
          onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
        />,
      )

      fireEvent.click(screen.getByRole('button', { name: 'Expand diff for a.ts' }))
      fireEvent.click(screen.getByRole('button', { name: 'Expand diff for b.ts' }))
      fireEvent.click(screen.getByRole('button', { name: 'Expand diff for a.ts' }))

      const joined = consoleError.mock.calls
        .flat()
        .map((entry) => String(entry))
        .join('\n')
      expect(joined).not.toContain('Maximum update depth exceeded')
      expect(joined).not.toContain('<path> attribute d: Expected number')
    } finally {
      consoleError.mockRestore()
    }
  })

  it('expands per-file canonical diff content without duplicating a shared blob', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'diff-multi-1',
              kind: 'diff',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 3,
              createdAt: '2026-04-01T00:00:03Z',
              updatedAt: '2026-04-01T00:00:03Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {
                semanticKind: 'fileChange',
                v2Kind: 'tool',
              },
              title: 'File changes',
              summaryText: null,
              changes: [
                {
                  path: 'src/a.ts',
                  kind: 'modify',
                  summary: null,
                  diff: ['diff --git a/src/a.ts b/src/a.ts', '@@ -1 +1 @@', '-const a = 1', '+const a = 2'].join(
                    '\n',
                  ),
                },
                {
                  path: 'src/b.ts',
                  kind: 'modify',
                  summary: null,
                  diff: [
                    'diff --git a/src/b.ts b/src/b.ts',
                    '@@ -1 +1 @@',
                    "-console.log('old')",
                    "+console.log('new')",
                  ].join('\n'),
                },
              ],
              files: [
                { path: 'src/a.ts', changeType: 'updated', summary: null, patchText: null },
                { path: 'src/b.ts', changeType: 'updated', summary: null, patchText: null },
              ],
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const diffRow = screen.getByTestId('conversation-v3-item-diff')
    expect(diffRow).toHaveTextContent('2 files changed')

    fireEvent.click(screen.getByRole('button', { name: 'Expand diff for a.ts' }))
    expect(diffRow).toHaveTextContent(/const\s+a\s*=\s*2/)

    fireEvent.click(screen.getByRole('button', { name: 'Expand diff for b.ts' }))
    expect(diffRow).toHaveTextContent(/console\.log\('new'\)/)
    expect(diffRow).not.toHaveTextContent('No diff excerpt for this file.')
  })

  it('keeps shell write commands as command cards when file payload is absent', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'tool-edit-shell-1',
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
              title:
                '"powershell.exe" -Command "@\'const ready = true;\'@ | Set-Content -Path tests/session.test.mjs"',
              toolName: 'powershell',
              callId: 'call-1',
              argumentsText:
                '"powershell.exe" -Command "@\'const ready = true;\'@ | Set-Content -Path tests/session.test.mjs"',
              outputText: 'PS > powershell.exe -Command ...',
              outputFiles: [],
              exitCode: 0,
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const toolRow = screen.getByTestId('conversation-v3-item-tool')
    expect(toolRow).toHaveTextContent(/set-content/i)
    fireEvent.click(screen.getByRole('button', { name: 'Expand command details' }))
    expect(screen.getByTestId('conversation-v3-tool-output-tool-edit-shell-1')).toBeInTheDocument()
    expect(screen.queryByLabelText('Copy diff')).not.toBeInTheDocument()
  })

  it('keeps pure commandExecution tools rendered as command cards', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'tool-cmd-1',
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
              outputText: 'line 1\nline 2',
              outputFiles: [],
              exitCode: null,
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const toolRow = screen.getByTestId('conversation-v3-item-tool')
    expect(within(toolRow).getByText('npm test')).toBeInTheDocument()
    expect(screen.getByTestId('conversation-v3-tool-output-tool-cmd-1')).toBeInTheDocument()
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

  it('renders assistant audit review JSON as summary text only', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          threadRole: 'audit',
          items: [
            {
              id: 'audit-msg-1',
              kind: 'message',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 1,
              createdAt: '2026-04-01T00:00:01Z',
              updatedAt: '2026-04-01T00:00:01Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              role: 'assistant',
              text: '{"summary":"Reviewed commit 738f17b and found no blocking issues."}',
              format: 'markdown',
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const row = screen.getByTestId('conversation-v3-item-message')
    expect(row).toHaveTextContent('Reviewed commit 738f17b and found no blocking issues.')
    expect(row.textContent ?? '').not.toContain('{"summary":')
  })

  it('renders review item JSON payload as summary text only', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          threadRole: 'audit',
          items: [
            {
              id: 'review-1',
              kind: 'review',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 2,
              createdAt: '2026-04-01T00:00:02Z',
              updatedAt: '2026-04-01T00:00:02Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              title: 'Review summary',
              text: '{"summary":"Static review passed with only non-blocking notes."}',
              disposition: null,
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const row = screen.getByTestId('conversation-v3-item-review')
    expect(row).toHaveTextContent('Static review passed with only non-blocking notes.')
    expect(row.textContent ?? '').not.toContain('{"summary":')
  })

  it('shows load-more history affordance and dispatches callback', () => {
    const onLoadMoreHistory = vi.fn()
    render(
      <MessagesV3
        snapshot={makeSnapshot()}
        isLoading={false}
        hasOlderHistory
        isLoadingHistory={false}
        onLoadMoreHistory={onLoadMoreHistory}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    const button = screen.getByTestId('messages-v3-load-more-history')
    expect(button).toHaveTextContent('Load older messages')
    fireEvent.click(button)
    expect(onLoadMoreHistory).toHaveBeenCalledTimes(1)
  })

  it('keeps heavy completed command rows collapsed by default and supports preview-to-full navigation', () => {
    const longOutput = Array.from({ length: 90 }, (_, index) => `line-${index + 1}`).join('\n')
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'tool-heavy-1',
              kind: 'tool',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 10,
              createdAt: '2026-04-01T00:00:10Z',
              updatedAt: '2026-04-01T00:00:10Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              toolType: 'commandExecution',
              title: 'Long command output',
              toolName: 'powershell',
              callId: 'call-heavy-1',
              argumentsText: 'Get-Content very-large.log',
              outputText: longOutput,
              outputFiles: [],
              exitCode: 0,
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.queryByTestId('conversation-v3-tool-output-tool-heavy-1')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Expand command details' }))
    expect(screen.getByTestId('conversation-v3-tool-output-tool-heavy-1')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'View full output' }))
    const dialog = screen.getByRole('dialog', { name: /Command output/ })
    expect(dialog).toHaveTextContent('line-1')
    expect(dialog).toHaveTextContent('line-90')

    fireEvent.click(within(dialog).getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog', { name: /Command output/ })).not.toBeInTheDocument()
  })

  it('keeps manual command collapse decision when heavy row transitions from in_progress to completed', () => {
    const heavyOutput = 'line\n'.repeat(20)
    const onResolveUserInput = vi.fn().mockResolvedValue(undefined)

    const { rerender } = render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'tool-manual-priority-1',
              kind: 'tool',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 20,
              createdAt: '2026-04-01T00:00:20Z',
              updatedAt: '2026-04-01T00:00:20Z',
              status: 'in_progress',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              toolType: 'commandExecution',
              title: 'Run build',
              toolName: 'npm',
              callId: 'call-priority-1',
              argumentsText: 'npm run build',
              outputText: heavyOutput,
              outputFiles: [],
              exitCode: null,
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={onResolveUserInput}
      />,
    )

    expect(screen.getByTestId('conversation-v3-tool-output-tool-manual-priority-1')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Collapse command details' }))
    expect(screen.queryByTestId('conversation-v3-tool-output-tool-manual-priority-1')).not.toBeInTheDocument()

    rerender(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'tool-manual-priority-1',
              kind: 'tool',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 20,
              createdAt: '2026-04-01T00:00:20Z',
              updatedAt: '2026-04-01T00:00:21Z',
              status: 'completed',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              toolType: 'commandExecution',
              title: 'Run build',
              toolName: 'npm',
              callId: 'call-priority-1',
              argumentsText: 'npm run build',
              outputText: heavyOutput,
              outputFiles: [],
              exitCode: 0,
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={onResolveUserInput}
      />,
    )

    expect(screen.queryByTestId('conversation-v3-tool-output-tool-manual-priority-1')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expand command details' })).toBeInTheDocument()
  })

  it('prefers streaming text lane override for assistant in-progress message rows', () => {
    const onResolveUserInput = vi.fn().mockResolvedValue(undefined)
    const laneKey = 'thread-1::msg-stream-1'

    useThreadByIdStoreV3.setState((state) => ({
      ...state,
      streamingTextLane: {
        ...state.streamingTextLane,
        [laneKey]: {
          threadId: 'thread-1',
          itemId: 'msg-stream-1',
          text: 'lane override text',
          updatedAtMs: Date.now(),
        },
      },
    }))

    render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'msg-stream-1',
              kind: 'message',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 9,
              createdAt: '2026-04-01T00:00:09Z',
              updatedAt: '2026-04-01T00:00:09Z',
              status: 'in_progress',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              role: 'assistant',
              text: 'snapshot base text',
              format: 'markdown',
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={onResolveUserInput}
      />,
    )

    expect(screen.getByText('lane override text')).toBeInTheDocument()
    expect(screen.queryByText('snapshot base text')).not.toBeInTheDocument()

    useThreadByIdStoreV3.setState((state) => ({
      ...state,
      streamingTextLane: {},
    }))
  })

  it('shows responding placeholder for assistant in-progress message when text is empty', () => {
    render(
      <MessagesV3
        snapshot={makeSnapshot({
          items: [
            {
              id: 'msg-stream-empty-1',
              kind: 'message',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 10,
              createdAt: '2026-04-01T00:00:10Z',
              updatedAt: '2026-04-01T00:00:10Z',
              status: 'in_progress',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              role: 'assistant',
              text: '',
              format: 'markdown',
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn().mockResolvedValue(undefined)}
      />,
    )

    expect(screen.getByText('Responding...')).toBeInTheDocument()
  })
})
