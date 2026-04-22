import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { SessionItem, SessionTurn } from '../../src/features/session_v2/contracts'
import { TranscriptPanel } from '../../src/features/session_v2/components/TranscriptPanel'

function baseTurn(items: SessionItem[], status: SessionTurn['status'] = 'completed'): SessionTurn {
  return {
    id: 'turn-1',
    threadId: 'thread-1',
    status,
    lastCodexStatus: status === 'inProgress' || status === 'waitingUserInput' ? 'inProgress' : 'completed',
    startedAtMs: 1,
    completedAtMs: 2,
    error: null,
    items,
  }
}

describe('TranscriptPanel', () => {
  it('renders native ThreadItem agent message text', () => {
    const item: SessionItem = {
      id: 'item-1',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Rendered from payload.text',
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item])]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByText('Rendered from payload.text')).toBeInTheDocument()
    expect(screen.queryByText('agentMessage')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Reasoning summary/i })).not.toBeInTheDocument()
  })

  it('renders delta-only payload while streaming', () => {
    const item: SessionItem = {
      id: 'item-2',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'inProgress',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        itemId: 'item-2',
        delta: 'Streaming delta text',
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([item], 'inProgress')]}
        itemsByTurn={{ 'thread-1:turn-1': [item] }}
      />,
    )

    expect(screen.getByText('Streaming delta text')).toBeInTheDocument()
  })

  it('summarizes tool items when turn is terminal', () => {
    const message: SessionItem = {
      id: 'item-msg',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Done.',
      },
    }
    const command1: SessionItem = {
      id: 'item-cmd-1',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'ls',
      },
    }
    const command2: SessionItem = {
      id: 'item-cmd-2',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'pwd',
      },
    }

    const items = [message, command1, command2]
    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    expect(screen.getByText('Done.')).toBeInTheDocument()
    expect(screen.getByText('Ran 2 commands')).toBeInTheDocument()
    expect(screen.queryByText('commandExecution')).not.toBeInTheDocument()
  })

  it('hides tool summary lines inside reasoning summary and expands timeline in original order', () => {
    const messageA: SessionItem = {
      id: 'item-msg-a',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Step A',
      },
    }
    const command1: SessionItem = {
      id: 'item-cmd-a',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'echo 1',
      },
    }
    const command2: SessionItem = {
      id: 'item-cmd-b',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'echo 2',
      },
    }
    const messageB: SessionItem = {
      id: 'item-msg-b',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Step B',
      },
    }
    const fileChange: SessionItem = {
      id: 'item-file',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'fileChange',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'fileChange',
        changes: [{ kind: 'edit', path: 'src/app.ts' }],
      },
    }
    const messageC: SessionItem = {
      id: 'item-msg-c',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Step C',
      },
    }

    const items = [messageA, command1, command2, messageB, fileChange, messageC]
    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    const reasoningSummaryToggle = screen.getByRole('button', { name: /Reasoning summary/i })
    expect(reasoningSummaryToggle).toBeInTheDocument()
    expect(screen.getByText('Step C')).toBeInTheDocument()
    expect(screen.queryByText('Step A')).not.toBeInTheDocument()
    expect(screen.queryByText('Step B')).not.toBeInTheDocument()
    expect(screen.queryByText('Ran 2 commands')).not.toBeInTheDocument()
    expect(screen.queryByText('Edited 1 file')).not.toBeInTheDocument()

    const allText = container.textContent ?? ''
    const posReasoningSummary = allText.indexOf('Reasoning summary')
    const posFileSummary = allText.indexOf('1 file changed')
    const posMessageC = allText.indexOf('Step C')

    expect(posReasoningSummary).toBeGreaterThanOrEqual(0)
    expect(posMessageC).toBeGreaterThan(posReasoningSummary)
    expect(posFileSummary).toBeGreaterThan(posMessageC)

    fireEvent.click(reasoningSummaryToggle)
    expect(screen.getByText('Step A')).toBeInTheDocument()
    expect(screen.getByText('Step B')).toBeInTheDocument()
    expect(screen.getByText('Ran 2 commands')).toBeInTheDocument()
    expect(screen.getByText('Edited 1 file')).toBeInTheDocument()

    const expandedText = container.textContent ?? ''
    const posExpandedStepA = expandedText.indexOf('Step A')
    const posExpandedRan = expandedText.indexOf('Ran 2 commands')
    const posExpandedStepB = expandedText.indexOf('Step B')
    const posExpandedEdited = expandedText.indexOf('Edited 1 file')
    const posExpandedStepC = expandedText.indexOf('Step C')
    expect(posExpandedStepA).toBeGreaterThanOrEqual(0)
    expect(posExpandedRan).toBeGreaterThan(posExpandedStepA)
    expect(posExpandedStepB).toBeGreaterThan(posExpandedRan)
    expect(posExpandedEdited).toBeGreaterThan(posExpandedStepB)
    expect(posExpandedStepC).toBeGreaterThan(posExpandedEdited)
  })

  it('renders context compaction marker instead of raw tool payload', () => {
    const before: SessionItem = {
      id: 'item-before',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Before compact',
      },
    }
    const compact: SessionItem = {
      id: 'item-compact',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'error',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'contextCompaction',
      },
    }
    const after: SessionItem = {
      id: 'item-after',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'After compact',
      },
    }

    const items = [before, compact, after]
    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    const reasoningSummaryToggle = screen.getByRole('button', { name: /Reasoning summary/i })
    fireEvent.click(reasoningSummaryToggle)
    expect(screen.getByText('Context automatically compacted')).toBeInTheDocument()
    expect(screen.queryByText('contextCompaction')).not.toBeInTheDocument()
  })

  it('renders end-of-turn files changed summary card', () => {
    const message: SessionItem = {
      id: 'item-msg',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'agentMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'agentMessage',
        text: 'Applied patches',
      },
    }
    const fileChangeA: SessionItem = {
      id: 'item-file-a',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'fileChange',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'fileChange',
        changes: [
          {
            path: 'frontend/src/a.ts',
            kind: 'modify',
            diff: ['@@', '-old line', '+new line', '+newer line'].join('\n'),
          },
        ],
      },
    }
    const fileChangeB: SessionItem = {
      id: 'item-file-b',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'fileChange',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'fileChange',
        changes: [
          {
            path: 'frontend/src/b.ts',
            kind: 'delete',
            diff: ['@@', '-gone'].join('\n'),
          },
        ],
      },
    }

    const items = [message, fileChangeA, fileChangeB]
    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn(items, 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': items }}
      />,
    )

    expect(screen.getByText('2 files changed')).toBeInTheDocument()
    expect(screen.getByText('frontend/src/a.ts')).toBeInTheDocument()
    expect(screen.getByText('frontend/src/b.ts')).toBeInTheDocument()
    const allText = container.textContent ?? ''
    expect(allText).toContain('+2')
    expect(allText).toContain('-2')
    expect(allText.indexOf('Applied patches')).toBeLessThan(allText.indexOf('2 files changed'))
  })

  it('keeps detailed tool cards while turn is running', () => {
    const command: SessionItem = {
      id: 'item-cmd-running',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'commandExecution',
      status: 'inProgress',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'commandExecution',
        command: 'npm test',
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([command], 'inProgress')]}
        itemsByTurn={{ 'thread-1:turn-1': [command] }}
      />,
    )

    expect(screen.getByText('commandExecution')).toBeInTheDocument()
    expect(screen.queryByText('Ran 1 command')).not.toBeInTheDocument()
  })

  it('collapses long user message and toggles show more/show less', () => {
    const longText = Array.from({ length: 20 }, (_, index) => `line-${index + 1}`).join('\n')
    const userItem: SessionItem = {
      id: 'item-user-long',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'userMessage',
      status: 'completed',
      createdAtMs: 1,
      updatedAtMs: 1,
      payload: {
        type: 'userMessage',
        text: longText,
      },
    }

    const { container } = render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([userItem], 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': [userItem] }}
      />,
    )

    expect(screen.getByRole('button', { name: 'Show more' })).toBeInTheDocument()
    expect(container.textContent ?? '').not.toContain('line-20')

    fireEvent.click(screen.getByRole('button', { name: 'Show more' }))
    expect(screen.getByRole('button', { name: 'Show less' })).toBeInTheDocument()
    expect(container.textContent ?? '').toContain('line-20')
  })

  it('renders user message detail row with copy action', () => {
    const userItem: SessionItem = {
      id: 'item-user-detail',
      threadId: 'thread-1',
      turnId: 'turn-1',
      kind: 'userMessage',
      status: 'completed',
      createdAtMs: Date.now(),
      updatedAtMs: Date.now(),
      payload: {
        type: 'userMessage',
        text: 'copy me',
      },
    }

    render(
      <TranscriptPanel
        threadId="thread-1"
        turns={[baseTurn([userItem], 'completed')]}
        itemsByTurn={{ 'thread-1:turn-1': [userItem] }}
      />,
    )

    expect(screen.getByLabelText('User message details')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Copy message' })).toBeInTheDocument()
  })
})
