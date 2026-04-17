import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ConversationMarkdown } from '../../src/features/conversation/components/ConversationMarkdown'

describe('ConversationMarkdown streaming staging', () => {
  it('renders plain text fallback while streaming and boundary is not safe', () => {
    render(
      <ConversationMarkdown
        content={'```ts\nconst x = 1\n'}
        streamingPlainTextMode
        parseTrace={{
          threadId: 'thread-1',
          itemId: 'msg-1',
          updatedAt: '2026-04-16T00:00:01Z',
          mode: 'message_markdown',
          source: 'test.streaming.markdown',
        }}
      />,
    )

    expect(screen.getByTestId('conversation-markdown-lazy-plain')).toBeInTheDocument()
    expect(screen.queryByRole('code')).not.toBeInTheDocument()
  })

  it('renders markdown when streaming boundary is safe', () => {
    render(
      <ConversationMarkdown
        content={'This is **done** with a closed sentence.\n'}
        streamingPlainTextMode
        parseTrace={{
          threadId: 'thread-1',
          itemId: 'msg-2',
          updatedAt: '2026-04-16T00:00:02Z',
          mode: 'message_markdown',
          source: 'test.streaming.markdown',
        }}
      />,
    )

    expect(screen.queryByTestId('conversation-markdown-lazy-plain')).not.toBeInTheDocument()
    expect(screen.getByText('done')).toBeInTheDocument()
  })
})
