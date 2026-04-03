import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { ThreadSnapshotV2, ToolItem, UserInputItem } from '../../src/api/types'
import { ConversationFeed } from '../../src/features/conversation/components/ConversationFeed'

function makeSnapshot(overrides: Partial<ThreadSnapshotV2> = {}): ThreadSnapshotV2 {
  return {
    projectId: 'project-1',
    nodeId: 'node-1',
    threadRole: 'execution',
    threadId: 'thread-1',
    activeTurnId: null,
    processingState: 'idle',
    snapshotVersion: 1,
    createdAt: '2026-03-28T00:00:00Z',
    updatedAt: '2026-03-28T00:00:00Z',
    lineage: {
      forkedFromThreadId: null,
      forkedFromNodeId: null,
      forkedFromRole: null,
      forkReason: null,
      lineageRootThreadId: 'thread-1',
    },
    items: [],
    pendingRequests: [],
    ...overrides,
  }
}

function makeCommandTool(overrides: Partial<ToolItem> = {}): ToolItem {
  return {
    id: 'tool-1',
    kind: 'tool',
    threadId: 'thread-1',
    turnId: 'turn-1',
    sequence: 1,
    createdAt: '2026-03-28T00:00:00Z',
    updatedAt: '2026-03-28T00:00:00Z',
    status: 'in_progress',
    source: 'upstream',
    tone: 'neutral',
    metadata: {},
    toolType: 'commandExecution',
    title: 'Run tests',
    toolName: 'powershell',
    callId: 'call-1',
    argumentsText: 'npm test',
    outputText: 'stdout\n',
    outputFiles: [],
    exitCode: null,
    ...overrides,
  }
}

function makeUserInput(overrides: Partial<UserInputItem> = {}): UserInputItem {
  return {
    id: 'input-1',
    kind: 'userInput',
    threadId: 'thread-1',
    turnId: 'turn-1',
    sequence: 10,
    createdAt: '2026-03-28T00:00:00Z',
    updatedAt: '2026-03-28T00:00:00Z',
    status: 'requested',
    source: 'upstream',
    tone: 'info',
    metadata: {},
    requestId: 'req-1',
    title: 'Need input',
    questions: [],
    answers: [],
    requestedAt: '2026-03-28T00:00:00Z',
    resolvedAt: null,
    ...overrides,
  }
}

describe('ConversationFeed', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('groups tool-heavy runs, filters empty reasoning, and keeps user input standalone', () => {
    render(
      <ConversationFeed
        snapshot={makeSnapshot({
          items: [
            makeCommandTool(),
            {
              id: 'reason-empty',
              kind: 'reasoning',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 2,
              createdAt: '2026-03-28T00:00:00Z',
              updatedAt: '2026-03-28T00:00:00Z',
              status: 'in_progress',
              source: 'upstream',
              tone: 'muted',
              metadata: {},
              summaryText: '   ',
              detailText: null,
            },
            {
              id: 'plan-1',
              kind: 'plan',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 3,
              createdAt: '2026-03-28T00:00:00Z',
              updatedAt: '2026-03-28T00:00:00Z',
              status: 'in_progress',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              title: null,
              text: 'Do the work',
              steps: [],
            },
            makeCommandTool({
              id: 'tool-2',
              sequence: 4,
              title: 'Apply patch',
              callId: 'call-2',
            }),
            makeUserInput(),
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn()}
      />,
    )

    expect(screen.getByTestId('conversation-tool-group-tool-1')).toBeInTheDocument()
    expect(screen.getByText('Run tests')).toBeInTheDocument()
    expect(screen.getByText('2 tools - 1 supporting items')).toBeInTheDocument()
    expect(screen.queryByTestId('conversation-item-reasoning')).not.toBeInTheDocument()
    expect(screen.getByTestId('conversation-item-user-input')).toBeInTheDocument()
  })

  it('hides empty assistant placeholders and shows semantic tool waiting text', () => {
    render(
      <ConversationFeed
        snapshot={makeSnapshot({
          activeTurnId: 'turn-1',
          processingState: 'running',
          items: [
            {
              id: 'msg-1',
              kind: 'message',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 1,
              createdAt: '2026-03-28T00:00:00Z',
              updatedAt: '2026-03-28T00:00:00Z',
              status: 'in_progress',
              source: 'upstream',
              tone: 'neutral',
              metadata: {},
              role: 'assistant',
              text: '   ',
              format: 'markdown',
            },
            makeCommandTool({
              id: 'tool-empty',
              sequence: 2,
              title: '',
              toolName: null,
              argumentsText: null,
              outputText: '',
            }),
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn()}
      />,
    )

    expect(screen.queryByTestId('conversation-item-message')).not.toBeInTheDocument()
    const toolRow = screen.getByTestId('conversation-item-tool')
    expect(within(toolRow).getByText('Running command')).toBeInTheDocument()
    expect(within(toolRow).getByText('Waiting for command output...')).toBeInTheDocument()
  })

  it('preserves manual collapse across live tool patches', () => {
    const { rerender } = render(
      <ConversationFeed
        snapshot={makeSnapshot({
          items: [makeCommandTool()],
          activeTurnId: 'turn-1',
          processingState: 'running',
        })}
        isLoading={false}
        onResolveUserInput={vi.fn()}
      />,
    )

    expect(screen.getByTestId('conversation-tool-output-tool-1')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Collapse' }))
    expect(screen.queryByTestId('conversation-tool-output-tool-1')).not.toBeInTheDocument()

    rerender(
      <ConversationFeed
        snapshot={makeSnapshot({
          items: [
            makeCommandTool({
              outputText: 'stdout\nmore output\n',
              updatedAt: '2026-03-28T00:00:02Z',
            }),
          ],
          activeTurnId: 'turn-1',
          processingState: 'running',
          updatedAt: '2026-03-28T00:00:02Z',
        })}
        isLoading={false}
        onResolveUserInput={vi.fn()}
      />,
    )

    expect(screen.queryByTestId('conversation-tool-output-tool-1')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Expand' })).toBeInTheDocument()
  })

  it('shows only the activity spinner while running (no reasoning caption or elapsed timer)', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-03-28T00:01:05Z'))

    render(
      <ConversationFeed
        snapshot={makeSnapshot({
          activeTurnId: 'turn-1',
          processingState: 'running',
          items: [
            {
              id: 'reason-1',
              kind: 'reasoning',
              threadId: 'thread-1',
              turnId: 'turn-1',
              sequence: 1,
              createdAt: '2026-03-28T00:00:00Z',
              updatedAt: '2026-03-28T00:00:30Z',
              status: 'in_progress',
              source: 'upstream',
              tone: 'muted',
              metadata: {},
              summaryText: '## Checking workspace',
              detailText: 'Looking at files',
            },
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn()}
      />,
    )

    const indicator = screen.getByTestId('conversation-working-indicator')
    expect(indicator).toBeInTheDocument()
    expect(indicator).not.toHaveTextContent('Checking workspace')
    expect(indicator).not.toHaveTextContent('Working...')
    expect(indicator.textContent).not.toMatch(/\d+:\d{2}/)
  })
})
