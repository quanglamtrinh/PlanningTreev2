import { useMemo, type Key } from 'react'
import { SharedMarkdownRenderer } from '../markdown/SharedMarkdownRenderer'
import styles from './FrameMarkdownViewer.module.css'

// Section types

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

type ShellPiece =
  | { kind: 'qa'; n: number; label: string; markdown: string }
  | { kind: 'qa-empty'; n: number; label: string }
  | { kind: 'body'; markdown: string }
  | { kind: 'section'; section: Exclude<Section, { kind: 'h1' } | { kind: 'h2' }> }

function buildShellPieces(sections: Section[]): ShellPiece[] {
  const pieces: ShellPiece[] = []
  let i = 0
  let n = 0

  while (i < sections.length) {
    const s = sections[i]
    if (s.kind === 'h1' || s.kind === 'h2') {
      n += 1
      const next = sections[i + 1]
      if (next?.kind === 'body') {
        pieces.push({ kind: 'qa', n, label: s.text, markdown: next.markdown })
        i += 2
      } else {
        pieces.push({ kind: 'qa-empty', n, label: s.text })
        i += 1
      }
      continue
    }
    if (s.kind === 'body') {
      pieces.push({ kind: 'body', markdown: s.markdown })
      i += 1
      continue
    }
    pieces.push({ kind: 'section', section: s })
    i += 1
  }

  return pieces
}

/** "Task title" / "1. Task title" blocks repeat the node header in frame shell. */
function isTaskTitleShellLabel(label: string): boolean {
  const t = label
    .toLowerCase()
    .replace(/\u00a0/g, ' ')
    .replace(/^\d+\.?\s*/, '')
    .trim()
  return t === 'task title'
}

function filterShellPieces(pieces: ShellPiece[]): ShellPiece[] {
  return pieces.filter((p) => {
    if (p.kind !== 'qa' && p.kind !== 'qa-empty') {
      return true
    }
    return !isTaskTitleShellLabel(p.label)
  })
}

// Parser

const ADR_HEADING_RE = /^### (.+)$/
const ADR_MATCH_RE = /\bADR(?:-|\u2013|\s)\d+\b|\bDecision\b/i

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


// Metadata shell: styled blocks (frame sections)

type ShellFrameBlockVariant =
  | 'userStory'
  | 'functional'
  | 'success'
  | 'outOfScope'
  | 'taskShaping'
  | 'default'

function shellFrameBlockVariant(label: string): ShellFrameBlockVariant {
  const t = label.toLowerCase().replace(/\u00a0/g, ' ')
  if (t.includes('user story') || (t.includes('problem') && t.includes('user'))) {
    return 'userStory'
  }
  if (t.includes('functional requirement')) {
    return 'functional'
  }
  if (t.includes('success criteria')) {
    return 'success'
  }
  if (t.includes('out of scope')) {
    return 'outOfScope'
  }
  if (t.includes('task-shaping') || t.includes('task shaping')) {
    return 'taskShaping'
  }
  return 'default'
}

function parseUserStoryItems(md: string): { title: string; description: string }[] {
  const t = md.trim()
  if (!t) {
    return []
  }
  if (!/^\s*###\s/m.test(t)) {
    return [{ title: '', description: t }]
  }
  const chunks = t
    .split(/(?=^###\s)/m)
    .map((c) => c.trim())
    .filter(Boolean)
  return chunks.map((chunk) => {
    const lines = chunk.split('\n')
    const title = lines[0].replace(/^###\s*/, '').trim()
    const description = lines.slice(1).join('\n').trim()
    return { title, description }
  })
}

function splitMarkdownListItems(md: string): string[] {
  const lines = md.split('\n')
  const items: string[] = []
  for (const line of lines) {
    const bullet = line.match(/^\s*[-*]\s+(.*)$/)
    const numbered = line.match(/^\s*\d+\.\s+(.*)$/)
    const m = bullet ?? numbered
    if (m) {
      items.push(m[1].trim())
    }
  }
  if (items.length === 0 && md.trim()) {
    return [md.trim()]
  }
  return items
}

type TaskShapingRow = { label: string; value: string }

function parseTaskShapingFields(md: string): TaskShapingRow[] {
  const lines = md.split('\n')
  const rows: TaskShapingRow[] = []
  const kv = /^\s*[-*]\s*(.+?):\s*(.*)$/
  for (const line of lines) {
    const m = line.match(kv)
    if (m) {
      rows.push({ label: m[1].trim(), value: m[2].trim() })
    }
  }
  if (rows.length > 0) {
    return rows
  }
  for (const line of lines) {
    const bullet = line.match(/^\s*[-*]\s+(.+)$/)
    if (bullet) {
      rows.push({ label: bullet[1].trim(), value: '' })
    }
  }
  return rows
}

function formatShapingFieldLabel(key: string): string {
  return key.replace(/\s+/g, ' ').trim().toUpperCase()
}


function IconUserStories() {
  return (
    <svg
      className={styles.shellSectionIcon}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  )
}

function IconFunctionalReq() {
  return (
    <svg className={styles.shellSectionIcon} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2M9 2h6v4H9V2Z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconSuccessCriteria() {
  return (
    <svg className={styles.shellSectionIcon} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10Z"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="m9 12 2 2 4-4"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function CheckCircleGlyph() {
  return (
    <svg className={styles.shellCheckCircleSvg} viewBox="0 0 20 20" fill="none" aria-hidden>
      <circle cx="10" cy="10" r="9" fill="currentColor" />
      <path
        d="M6 10.2 8.5 12.7 14.2 7"
        stroke="#fff"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconOutOfScope() {
  return (
    <svg
      className={styles.shellSectionIconMuted}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.75" />
      <path d="M8 12h8" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" />
    </svg>
  )
}

function IconTaskShaping() {
  return (
    <svg className={styles.shellSectionIcon} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M4 8h16M4 12h16M4 16h16"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
      <circle cx="15" cy="8" r="2.25" fill="currentColor" />
      <circle cx="9" cy="12" r="2.25" fill="currentColor" />
      <circle cx="14" cy="16" r="2.25" fill="currentColor" />
    </svg>
  )
}

function ShellUserStoriesSection({
  label,
  markdown,
  projectRootPath,
}: {
  label: string
  markdown: string
  projectRootPath?: string
}) {
  const items = parseUserStoryItems(markdown)
  return (
    <section className={styles.shellStyledSection}>
      <div className={styles.shellSectionHeading}>
        <IconUserStories />
        <span className={styles.shellSectionTitle}>{label}</span>
      </div>
      {items.length === 0 ? (
        <span className={styles.shellQaEmpty}>No content</span>
      ) : (
        <div className={styles.shellUserStoryList}>
          {items.map((item, i) => (
            <div key={i} className={styles.shellUserStoryRow}>
              <span className={styles.shellUserStoryIndex}>{String(i + 1).padStart(2, '0')}</span>
              <div className={styles.shellUserStoryBody}>
                {item.title ? (
                  <div className={styles.shellUserStoryTitle}>{item.title}</div>
                ) : null}
                {item.description ? (
                  <div className={styles.shellUserStoryDesc}>
                    <SharedMarkdownRenderer
                      content={item.description}
                      projectRootPath={projectRootPath}
                      variant="context-shell"
                    />
                  </div>
                ) : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function ShellFunctionalRequirementsSection({
  label,
  markdown,
  projectRootPath,
}: {
  label: string
  markdown: string
  projectRootPath?: string
}) {
  const items = splitMarkdownListItems(markdown)
  return (
    <section className={styles.shellStyledSection}>
      <div className={styles.shellSectionHeading}>
        <IconFunctionalReq />
        <span className={styles.shellSectionTitle}>{label}</span>
      </div>
      {items.length === 0 ? (
        <span className={styles.shellQaEmpty}>No content</span>
      ) : (
        <ul className={styles.shellCheckList}>
          {items.map((item, i) => (
            <li key={i} className={styles.shellCheckListItem}>
              <span className={styles.shellCheckListGlyph} aria-hidden>
                <CheckCircleGlyph />
              </span>
              <div className={styles.shellCheckListBody}>
                <SharedMarkdownRenderer
                  content={item}
                  projectRootPath={projectRootPath}
                  variant="context-shell"
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ShellSuccessCriteriaSection({
  label,
  markdown,
  projectRootPath,
}: {
  label: string
  markdown: string
  projectRootPath?: string
}) {
  const items = splitMarkdownListItems(markdown)
  return (
    <section className={styles.shellStyledSection}>
      <div className={styles.shellSectionHeading}>
        <IconSuccessCriteria />
        <span className={styles.shellSectionTitle}>{label}</span>
      </div>
      {items.length === 0 ? (
        <span className={styles.shellQaEmpty}>No content</span>
      ) : (
        <ul className={styles.shellCheckList}>
          {items.map((item, i) => (
            <li key={i} className={styles.shellCheckListItem}>
              <span className={styles.shellCheckListGlyph} aria-hidden>
                <CheckCircleGlyph />
              </span>
              <div className={styles.shellCheckListBody}>
                <SharedMarkdownRenderer
                  content={item}
                  projectRootPath={projectRootPath}
                  variant="context-shell"
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ShellOutOfScopeSection({
  label,
  markdown,
  projectRootPath,
}: {
  label: string
  markdown: string
  projectRootPath?: string
}) {
  const items = splitMarkdownListItems(markdown)
  return (
    <section className={styles.shellStyledSection}>
      <div className={styles.shellSectionHeading}>
        <IconOutOfScope />
        <span className={styles.shellSectionTitle}>{label}</span>
      </div>
      {items.length === 0 ? (
        <span className={styles.shellQaEmpty}>No content</span>
      ) : (
        <ul className={styles.shellOosList}>
          {items.map((item, i) => (
            <li key={i} className={styles.shellOosItem}>
              <span className={styles.shellOosMinusIcon} aria-hidden>
                <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <circle cx="8" cy="8" r="7.25" stroke="currentColor" strokeWidth="1.35" />
                  <path d="M5 8h6" stroke="currentColor" strokeWidth="1.35" strokeLinecap="round" />
                </svg>
              </span>
              <div className={styles.shellOosText}>
                <SharedMarkdownRenderer
                  content={item}
                  projectRootPath={projectRootPath}
                  variant="context-shell"
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ShellTaskShapingSection({ label, markdown }: { label: string; markdown: string }) {
  const rows = parseTaskShapingFields(markdown)
  return (
    <section className={styles.shellStyledSection}>
      <div className={styles.shellSectionHeading}>
        <IconTaskShaping />
        <span className={styles.shellSectionTitle}>{label}</span>
      </div>
      {rows.length === 0 ? (
        <span className={styles.shellQaEmpty}>No content</span>
      ) : (
        <div className={styles.shellTsfGrid}>
          {rows.map((row, i) => (
            <div key={`${row.label}-${i}`} className={styles.shellTsfCard}>
              <div className={styles.shellTsfLabel}>{formatShapingFieldLabel(row.label)}</div>
              {row.value ? (
                <div className={styles.shellTsfValue}>{row.value}</div>
              ) : (
                <div className={styles.shellTsfValueEmpty}>Unset</div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  )
}

function renderSectionBlock(section: Section, key: Key, projectRootPath?: string) {
  if (section.kind === 'h1') {
    return <h1 key={key} className={styles.h1}>{section.text}</h1>
  }

  if (section.kind === 'h2') {
    return <h2 key={key} className={styles.h2}>{section.text}</h2>
  }

  if (section.kind === 'callout') {
    return (
      <div key={key} className={styles.callout}>
        <span className={styles.calloutLabel}>{section.label}</span>
        {section.body && (
          <div className={styles.calloutBody}>
            <SharedMarkdownRenderer
              content={section.body}
              projectRootPath={projectRootPath}
              variant="context-shell"
            />
          </div>
        )}
      </div>
    )
  }

  if (section.kind === 'decision-grid') {
    return (
      <div key={key} className={styles.decisionGrid}>
        {section.cards.map((card, j) => (
          <div key={j} className={styles.decisionCard}>
            <span className={styles.decisionEyebrow}>{card.eyebrow}</span>
            {card.title && (
              <div className={styles.decisionTitle}>{card.title}</div>
            )}
            {card.body && (
              <div className={styles.decisionBody}>
                <SharedMarkdownRenderer
                  content={card.body}
                  projectRootPath={projectRootPath}
                  variant="context-shell"
                />
              </div>
            )}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div key={key} className={styles.body}>
      <SharedMarkdownRenderer
        content={section.markdown}
        projectRootPath={projectRootPath}
        variant="context-shell"
      />
    </div>
  )
}

// Component

export function FrameMarkdownViewer({
  content,
  shellStyle = false,
  projectRootPath,
}: {
  content: string
  shellStyle?: boolean
  projectRootPath?: string
}) {
  const sections = useMemo(() => parseFrameContent(content), [content])
  const shellPieces = useMemo(
    () => (shellStyle ? filterShellPieces(buildShellPieces(sections)) : null),
    [sections, shellStyle],
  )

  if (!content.trim()) {
    return null
  }

  if (shellStyle && shellPieces) {
    return (
      <div className={`${styles.viewer} ${styles.viewerShell}`}>
        {shellPieces.map((piece, i) => {
          if (piece.kind === 'qa') {
            const key = `qa-${piece.n}-${piece.label}`
            const blockVariant = shellFrameBlockVariant(piece.label)
            if (blockVariant === 'userStory') {
              return (
                <ShellUserStoriesSection
                  key={key}
                  label={piece.label}
                  markdown={piece.markdown}
                  projectRootPath={projectRootPath}
                />
              )
            }
            if (blockVariant === 'functional') {
              return (
                <ShellFunctionalRequirementsSection
                  key={key}
                  label={piece.label}
                  markdown={piece.markdown}
                  projectRootPath={projectRootPath}
                />
              )
            }
            if (blockVariant === 'success') {
              return (
                <ShellSuccessCriteriaSection
                  key={key}
                  label={piece.label}
                  markdown={piece.markdown}
                  projectRootPath={projectRootPath}
                />
              )
            }
            if (blockVariant === 'outOfScope') {
              return (
                <ShellOutOfScopeSection
                  key={key}
                  label={piece.label}
                  markdown={piece.markdown}
                  projectRootPath={projectRootPath}
                />
              )
            }
            if (blockVariant === 'taskShaping') {
              return <ShellTaskShapingSection key={key} label={piece.label} markdown={piece.markdown} />
            }
            return (
              <div key={key} className={styles.shellQaItem}>
                <span className={styles.shellQaLabel}>
                  {piece.n}. {piece.label}
                </span>
                <div className={styles.shellQaValue}>
                  <SharedMarkdownRenderer
                    content={piece.markdown}
                    projectRootPath={projectRootPath}
                    variant="context-shell"
                  />
                </div>
              </div>
            )
          }
          if (piece.kind === 'qa-empty') {
            const qaeKey = `qae-${piece.n}-${piece.label}`
            const emptyVariant = shellFrameBlockVariant(piece.label)
            if (emptyVariant === 'outOfScope') {
              return (
                <ShellOutOfScopeSection
                  key={qaeKey}
                  label={piece.label}
                  markdown=""
                  projectRootPath={projectRootPath}
                />
              )
            }
            if (emptyVariant === 'taskShaping') {
              return <ShellTaskShapingSection key={qaeKey} label={piece.label} markdown="" />
            }
            return (
              <div key={qaeKey} className={styles.shellQaItem}>
                <span className={styles.shellQaLabel}>
                  {piece.n}. {piece.label}
                </span>
                <span className={styles.shellQaEmpty}>No content</span>
              </div>
            )
          }
          if (piece.kind === 'body') {
            return (
              <div key={`body-${i}`} className={styles.shellBody}>
                <SharedMarkdownRenderer
                  content={piece.markdown}
                  projectRootPath={projectRootPath}
                  variant="context-shell"
                />
              </div>
            )
          }
          return renderSectionBlock(piece.section, `sec-${i}`, projectRootPath)
        })}
      </div>
    )
  }

  return (
    <div className={styles.viewer}>
      {sections.map((section, i) => renderSectionBlock(section, i, projectRootPath))}
    </div>
  )
}
