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

  it('renders command-based file writes as file-change cards when path can be inferred', () => {
    render(
      <ConversationFeed
        snapshot={makeSnapshot({
          items: [
            makeCommandTool({
              id: 'tool-write-1',
              status: 'completed',
              argumentsText:
                '"powershell.exe" -Command "@\'content\'@ | Set-Content -Path tests/session.test.mjs"',
              outputText: '',
              outputFiles: [],
            }),
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn()}
      />,
    )

    const toolRow = screen.getByTestId('conversation-item-tool')
    expect(within(toolRow).getByText('session.test.mjs')).toBeInTheDocument()
    expect(within(toolRow).getByLabelText('Copy diff')).toBeInTheDocument()
    expect(screen.queryByTestId('conversation-tool-output-tool-write-1')).not.toBeInTheDocument()
  })

  it('prefers inferred file payload over raw command output for shell-write commands', () => {
    render(
      <ConversationFeed
        snapshot={makeSnapshot({
          items: [
            makeCommandTool({
              id: 'tool-write-2',
              status: 'completed',
              argumentsText:
                '"powershell.exe" -Command "@\'const ready = true;\'@ | Set-Content -Path src/app.ts"',
              outputText: 'PS > powershell.exe -Command ...',
              outputFiles: [],
            }),
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn()}
      />,
    )

    fireEvent.click(screen.getByRole('button', { name: 'Expand diff for app.ts' }))
    const toolRow = screen.getByTestId('conversation-item-tool')
    expect(toolRow).toHaveTextContent(/const\s+ready\s*=\s*true;/)
    expect(toolRow).not.toHaveTextContent(/PS > powershell\.exe/i)
  })

  it('shows per-file diff content and +/- stats for multi-file patch payloads', () => {
    render(
      <ConversationFeed
        snapshot={makeSnapshot({
          items: [
            makeCommandTool({
              id: 'tool-multi-1',
              status: 'completed',
              title: 'apply_patch',
              toolName: 'apply_patch',
              argumentsText: [
                '*** Begin Patch',
                '*** Update File: src/a.ts',
                '@@',
                '-const a = 1',
                '+const a = 2',
                '*** Update File: src/b.ts',
                '@@',
                "-console.log('old')",
                "+console.log('new')",
                '*** End Patch',
              ].join('\n'),
              outputText: 'Updated 2 files',
              outputFiles: [
                { path: 'src/a.ts', changeType: 'updated', summary: null },
                { path: 'src/b.ts', changeType: 'updated', summary: null },
              ],
              exitCode: 0,
            }),
          ],
        })}
        isLoading={false}
        onResolveUserInput={vi.fn()}
      />,
    )

    const toolRow = screen.getByTestId('conversation-item-tool')
    expect(within(toolRow).getByText('2 files changed')).toBeInTheDocument()
    expect(within(toolRow).getAllByText('+1').length).toBeGreaterThanOrEqual(2)
    expect(within(toolRow).getAllByText('-1').length).toBeGreaterThanOrEqual(2)

    fireEvent.click(within(toolRow).getByRole('button', { name: 'Expand diff for a.ts' }))
    expect(toolRow).toHaveTextContent(/const\s+a\s*=\s*2/)

    fireEvent.click(within(toolRow).getByRole('button', { name: 'Expand diff for b.ts' }))
    expect(toolRow).toHaveTextContent(/console\.log\('new'\)/)
    expect(toolRow).not.toHaveTextContent('No diff excerpt for this file.')
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
