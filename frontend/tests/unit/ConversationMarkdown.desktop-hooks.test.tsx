import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ConversationMarkdown } from '../../src/features/conversation/components/ConversationMarkdown'
import {
  resetConversationMarkdownDesktopHooks,
  setConversationMarkdownDesktopHooks,
} from '../../src/features/conversation/components/markdownDesktopHooks'

afterEach(() => {
  resetConversationMarkdownDesktopHooks()
})

describe('ConversationMarkdown desktop hooks', () => {
  it('keeps default no-op behavior when hooks are not configured', () => {
    render(<ConversationMarkdown content={'[doc](https://example.com)'} />)

    const link = screen.getByRole('link', { name: 'doc' })
    expect(link).toBeInTheDocument()
    expect(link.getAttribute('href')).toBe('https://example.com')
  })

  it('formats local file links with line location into filename labels', () => {
    render(
      <ConversationMarkdown
        content={'[/Users/example/workspace/src/ComposerPane.tsx:290](/Users/example/workspace/src/ComposerPane.tsx:290)'}
      />,
    )

    const localLink = screen.getByRole('link', { name: 'ComposerPane.tsx (line 290)' })
    expect(localLink).toBeInTheDocument()
    expect(localLink.getAttribute('href')).toBe('/Users/example/workspace/src/ComposerPane.tsx:290')
  })

  it('invokes desktop-prep hooks for local file, thread link, image lightbox, and code copy', () => {
    const openLocalFile = vi.fn().mockReturnValue(true)
    const onFileLinkContextMenu = vi.fn()
    const openThreadLink = vi.fn().mockReturnValue(true)
    const openImageLightbox = vi.fn().mockReturnValue(true)
    const copyCodeBlock = vi.fn()

    setConversationMarkdownDesktopHooks({
      openLocalFile,
      onFileLinkContextMenu,
      openThreadLink,
      openImageLightbox,
      copyCodeBlock,
    })

    render(
      <ConversationMarkdown
        content={[
          '[open file](file:///C:/workspace/project/readme.md)',
          '[jump thread](thread://exec-thread-1)',
          '![diagram](https://example.com/diagram.png)',
          '```ts',
          'console.log("hello")',
          '```',
        ].join('\n\n')}
      />,
    )

    const fileLink = screen.getByRole('link', { name: 'open file' })
    fireEvent.click(fileLink)
    fireEvent.contextMenu(fileLink)

    const threadLink = screen.getByRole('link', { name: 'jump thread' })
    fireEvent.click(threadLink)

    const image = screen.getByRole('img', { name: 'diagram' })
    fireEvent.click(image)

    const pre = document.querySelector('pre')
    expect(pre).toBeTruthy()
    if (pre) {
      fireEvent.doubleClick(pre)
    }

    expect(openLocalFile).toHaveBeenCalledTimes(1)
    expect(openLocalFile.mock.calls[0][0].path).toBe('C:/workspace/project/readme.md')
    expect(onFileLinkContextMenu).toHaveBeenCalledTimes(1)
    expect(openThreadLink).toHaveBeenCalledTimes(1)
    expect(openThreadLink.mock.calls[0][0].threadId).toBe('exec-thread-1')
    expect(openImageLightbox).toHaveBeenCalledTimes(1)
    expect(copyCodeBlock).toHaveBeenCalledTimes(1)
    expect(copyCodeBlock.mock.calls[0][0].code).toContain('console.log("hello")')
  })
})
