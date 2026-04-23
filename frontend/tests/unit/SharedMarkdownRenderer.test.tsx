import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SharedMarkdownRenderer } from '../../src/features/markdown/SharedMarkdownRenderer'

describe('SharedMarkdownRenderer', () => {
  it('renders remote links as markdown anchors', () => {
    render(
      <SharedMarkdownRenderer content={'[Docs](https://example.com/docs)'} variant="document" />,
    )

    const link = screen.getByRole('link', { name: 'Docs' })
    expect(link).toBeInTheDocument()
    expect(link.getAttribute('href')).toBe('https://example.com/docs')
  })

  it('renders local links as line labels and hides markdown label', () => {
    render(
      <SharedMarkdownRenderer
        content={'[Open this file](file:///Users/example/workspace/frame.md#L74C3)'}
        projectRootPath="/Users/example/workspace"
        variant="document"
      />,
    )

    expect(screen.queryByRole('link', { name: /open this file/i })).not.toBeInTheDocument()
    expect(screen.queryByText('Open this file')).not.toBeInTheDocument()
    const localLink = screen.getByRole('link', { name: 'frame.md (line 74, col 3)' })
    expect(localLink).toBeInTheDocument()
    expect(localLink.getAttribute('href')).toBe('file:///Users/example/workspace/frame.md#L74C3')
  })

  it('applies syntax highlight classes to fenced code blocks', () => {
    const { container } = render(
      <SharedMarkdownRenderer
        content={'```ts\nconst value = 42\n```'}
        variant="document"
      />,
    )

    const codeBlock = container.querySelector('pre code')
    expect(codeBlock).toBeTruthy()
    expect(codeBlock?.textContent).toContain('const value = 42')

    const className = codeBlock?.getAttribute('class') ?? ''
    const hasRootHighlightClass = /\bhljs\b/.test(className)
    const hasTokenHighlightClass = container.querySelector('[class*="hljs-"]') !== null
    const hasLanguageClass = /\blanguage-ts\b/.test(className)
    expect(hasRootHighlightClass || hasTokenHighlightClass || hasLanguageClass).toBe(true)
  })
})
