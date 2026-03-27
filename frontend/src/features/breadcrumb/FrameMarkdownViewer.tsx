import { useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import type { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import styles from './FrameMarkdownViewer.module.css'

// ─── Section types ─────────────────────────────────────────────────

type Section =
  | { kind: 'h1'; text: string }
  | { kind: 'h2'; text: string }
  | { kind: 'callout'; label: string; body: string }
  | { kind: 'decision-grid'; cards: DecisionCard[] }
  | { kind: 'body'; markdown: string }

type DecisionCard = {
  eyebrow: string
  title: string
  body: string
}

// ─── Parser ────────────────────────────────────────────────────────

const ADR_HEADING_RE = /^### (.+)$/
const ADR_MATCH_RE = /\bADR[-–\s]\d+\b|\bDecision\b/i

function parseDecisionHeading(heading: string): { eyebrow: string; title: string } {
  const colonIdx = heading.indexOf(':')
  if (colonIdx > -1) {
    return {
      eyebrow: heading.slice(0, colonIdx).trim(),
      title: heading.slice(colonIdx + 1).trim(),
    }
  }
  return { eyebrow: heading, title: '' }
}

function parseFrameContent(content: string): Section[] {
  const lines = content.split('\n')
  const sections: Section[] = []

  let bodyLines: string[] = []
  let calloutLines: string[] | null = null
  let decisionCards: DecisionCard[] | null = null
  let currentCard: { eyebrow: string; title: string; bodyLines: string[] } | null = null

  function flushBody() {
    const md = bodyLines.join('\n').trimEnd()
    if (md.trim()) sections.push({ kind: 'body', markdown: md })
    bodyLines = []
  }

  function flushCallout() {
    if (!calloutLines || calloutLines.length === 0) { calloutLines = null; return }
    const [first, ...rest] = calloutLines
    const label = (first ?? '').replace(/^\*\*|\*\*$/g, '').trim() || 'Note'
    const body = rest.join('\n').trim()
    if (label || body) sections.push({ kind: 'callout', label, body })
    calloutLines = null
  }

  function flushCurrentCard() {
    if (!currentCard || !decisionCards) return
    decisionCards.push({
      eyebrow: currentCard.eyebrow,
      title: currentCard.title,
      body: currentCard.bodyLines.join('\n').trim(),
    })
    currentCard = null
  }

  function flushDecisions() {
    if (!decisionCards) return
    flushCurrentCard()
    if (decisionCards.length > 0) {
      sections.push({ kind: 'decision-grid', cards: decisionCards })
    }
    decisionCards = null
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const isBlockquote = line.startsWith('> ') || line === '>'
    const wasBlockquote = calloutLines !== null

    // Blockquote ended
    if (!isBlockquote && wasBlockquote) {
      flushCallout()
    }

    // H1
    if (/^# [^#]/.test(line)) {
      flushCallout(); flushDecisions(); flushBody()
      sections.push({ kind: 'h1', text: line.slice(2).trim() })
      continue
    }

    // H2
    if (/^## [^#]/.test(line)) {
      flushCallout(); flushDecisions(); flushBody()
      sections.push({ kind: 'h2', text: line.slice(3).trim() })
      continue
    }

    // H3 matching ADR / Decision pattern
    const h3Match = line.match(ADR_HEADING_RE)
    if (h3Match && ADR_MATCH_RE.test(h3Match[1])) {
      flushCallout(); flushBody()
      if (!decisionCards) decisionCards = []
      flushCurrentCard()
      const { eyebrow, title } = parseDecisionHeading(h3Match[1])
      currentCard = { eyebrow, title, bodyLines: [] }
      continue
    }

    // Regular H3 or deeper heading (non-decision)
    if (/^#{3,6} /.test(line)) {
      flushCallout(); flushDecisions(); flushBody()
      bodyLines.push(line)
      continue
    }

    // Blockquote line
    if (isBlockquote) {
      flushDecisions(); flushBody()
      if (!calloutLines) calloutLines = []
      calloutLines.push(line.startsWith('> ') ? line.slice(2) : '')
      continue
    }

    // Content inside a decision card
    if (currentCard) {
      currentCard.bodyLines.push(line)
      continue
    }

    // Regular body
    bodyLines.push(line)
  }

  flushCallout()
  flushDecisions()
  flushBody()

  return sections
}

// ─── Shared markdown components ────────────────────────────────────

const mdComponents: Components = {
  p: ({ children }) => <p className={styles.p}>{children}</p>,
  strong: ({ children }) => <strong className={styles.strong}>{children}</strong>,
  ul: ({ children }) => (
    <div className={styles.listCard}>
      <ul className={styles.ul}>{children}</ul>
    </div>
  ),
  ol: ({ children }) => (
    <div className={styles.listCard}>
      <ol className={styles.ol}>{children}</ol>
    </div>
  ),
  li: ({ children }) => <li className={styles.li}>{children}</li>,
  h3: ({ children }) => <h3 className={styles.h3}>{children}</h3>,
  h4: ({ children }) => <h4 className={styles.h4}>{children}</h4>,
  code: ({ className, children }) => {
    if (className?.startsWith('language-')) {
      return <code className={styles.codeBlock}>{children}</code>
    }
    return <code className={styles.inlineCode}>{children}</code>
  },
  pre: ({ children }) => <pre className={styles.pre}>{children}</pre>,
}

// ─── Component ─────────────────────────────────────────────────────

export function FrameMarkdownViewer({ content }: { content: string }) {
  const sections = useMemo(() => parseFrameContent(content), [content])

  if (!content.trim()) {
    return null
  }

  return (
    <div className={styles.viewer}>
      {sections.map((section, i) => {
        if (section.kind === 'h1') {
          return <h1 key={i} className={styles.h1}>{section.text}</h1>
        }

        if (section.kind === 'h2') {
          return <h2 key={i} className={styles.h2}>{section.text}</h2>
        }

        if (section.kind === 'callout') {
          return (
            <div key={i} className={styles.callout}>
              <span className={styles.calloutLabel}>{section.label}</span>
              {section.body && (
                <div className={styles.calloutBody}>
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                    {section.body}
                  </ReactMarkdown>
                </div>
              )}
            </div>
          )
        }

        if (section.kind === 'decision-grid') {
          return (
            <div key={i} className={styles.decisionGrid}>
              {section.cards.map((card, j) => (
                <div key={j} className={styles.decisionCard}>
                  <span className={styles.decisionEyebrow}>{card.eyebrow}</span>
                  {card.title && (
                    <div className={styles.decisionTitle}>{card.title}</div>
                  )}
                  {card.body && (
                    <div className={styles.decisionBody}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                        {card.body}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )
        }

        return (
          <div key={i} className={styles.body}>
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {section.markdown}
            </ReactMarkdown>
          </div>
        )
      })}
    </div>
  )
}
