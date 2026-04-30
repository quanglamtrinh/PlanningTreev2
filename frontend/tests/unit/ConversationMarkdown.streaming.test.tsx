import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { ConversationMarkdown } from '../../src/features/conversation/components/ConversationMarkdown'

describe('ConversationMarkdown streaming staging', () => {
  it('renders markdown code blocks directly after streaming fallback removal', () => {
    const { container } = render(
      <ConversationMarkdown
        content={'```ts\nconst x = 1\n'}
      />,
    )

    expect(container.querySelector('code.language-ts')).toHaveTextContent('const x = 1')
  })

  it('renders inline markdown formatting', () => {
    render(
      <ConversationMarkdown
        content={'This is **done** with a closed sentence.\n'}
      />,
    )

    expect(screen.getByText('done')).toBeInTheDocument()
  })
})
