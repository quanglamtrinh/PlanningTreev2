import { render, screen } from '@testing-library/react'
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
    render(
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
})
