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

    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.getByText('```css', { exact: false })).toBeInTheDocument()
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

    expect(screen.getByText('Summary')).toBeInTheDocument()
    expect(screen.getByText('```ts', { exact: false })).toBeInTheDocument()
    expect(screen.getByText('const answer = 42', { exact: false }).closest('pre')).not.toBeNull()
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

  it('renders plan items and still shows the final summary content', () => {
    render(
      <MessageFeed
        messages={[
          makeAssistantMessage({
            content: 'Implemented the task.',
            parts: [
              {
                type: 'plan_item',
                item_id: 'plan-1',
                content: 'Inspect workspace',
                is_streaming: false,
                timestamp: '2026-03-20T00:00:00Z',
              },
              {
                type: 'tool_call',
                tool_name: 'write_file',
                arguments: { path: 'main.js' },
                call_id: null,
                status: 'completed',
              },
            ],
          }),
        ]}
      />,
    )

    expect(screen.getByText('Inspect workspace')).toBeInTheDocument()
    expect(screen.getByText('Implemented the task.')).toBeInTheDocument()
  })
})
