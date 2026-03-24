import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ChatMessage } from '../../src/api/types'
import { MessageFeed } from '../../src/features/breadcrumb/MessageFeed'

function makeAssistantMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    message_id: 'assistant-1',
    role: 'assistant',
    content: '',
    status: 'completed',
    error: null,
    turn_id: 'turn-1',
    created_at: '2026-03-20T00:00:00Z',
    updated_at: '2026-03-20T00:00:00Z',
    ...overrides,
  }
}

function makeSystemMessage(overrides: Partial<ChatMessage> = {}): ChatMessage {
  return {
    message_id: 'system-1',
    role: 'system',
    content: 'Canonical task context',
    status: 'completed',
    error: null,
    turn_id: null,
    created_at: '2026-03-20T00:00:00Z',
    updated_at: '2026-03-20T00:00:00Z',
    ...overrides,
  }
}

describe('MessageFeed', () => {
  it('renders fenced code blocks from flat content fallback', () => {
    render(
      <MessageFeed
        messages={[
          makeAssistantMessage({
            content: [
              'Example:',
              '',
              '```css',
              ':root {',
              '  --bg: #f7f3ee;',
              '}',
              '```',
            ].join('\n'),
          }),
        ]}
      />,
    )

    expect(screen.queryByText('```css')).not.toBeInTheDocument()
    expect(screen.getByText('css')).toBeInTheDocument()
    expect(screen.getByText('--bg: #f7f3ee;', { exact: false }).closest('pre')).not.toBeNull()
  })

  it('renders fenced code blocks from assistant_text parts', () => {
    render(
      <MessageFeed
        messages={[
          makeAssistantMessage({
            parts: [
              {
                type: 'assistant_text',
                content: ['```ts', 'const answer = 42', '```'].join('\n'),
                is_streaming: false,
              },
            ],
          }),
        ]}
      />,
    )

    expect(screen.queryByText('```ts')).not.toBeInTheDocument()
    expect(screen.getByText('ts')).toBeInTheDocument()
    expect(screen.getByText('const answer = 42').closest('pre')).not.toBeNull()
  })

  it('renders system messages as thread context blocks', () => {
    render(
      <MessageFeed
        messages={[
          makeSystemMessage({
            content: 'Checkpoint context:\n- SHA: `sha256:abc123`\n- Summary: Accepted',
          }),
        ]}
      />,
    )

    expect(screen.getByText('Context')).toBeInTheDocument()
    expect(screen.getByText('Checkpoint context:')).toBeInTheDocument()
    expect(screen.getByText('sha256:abc123')).toBeInTheDocument()
  })
})
