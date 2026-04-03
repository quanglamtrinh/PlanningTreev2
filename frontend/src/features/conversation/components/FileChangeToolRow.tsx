import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { ToolItem, ToolOutputFile } from '../../../api/types'
import styles from './ConversationFeed.module.css'
import {
  getToolHeadline,
  getToolPlaceholderText,
  hasMeaningfulToolContent,
} from './toolPresentation'

function normalizeText(value: string | null | undefined): string {
  return String(value ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim()
}

function basename(path: string): string {
  const normalized = path.replace(/\\/g, '/')
  const segment = normalized.split('/').pop()
  return segment?.trim() || path
}

function diffStatsFromText(text: string): { added: number; removed: number } {
  let added = 0
  let removed = 0
  for (const line of text.split('\n')) {
    if (line.startsWith('+') && !line.startsWith('+++')) {
      added += 1
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      removed += 1
    }
  }
  return { added, removed }
}

function parseStatsFromSummary(summary: string | null | undefined): { added: number; removed: number } | null {
  if (!summary) {
    return null
  }
  const m = summary.match(/\+\s*(\d+)[^\d-]*-\s*(\d+)/)
  if (!m) {
    return null
  }
  return { added: Number(m[1]), removed: Number(m[2]) }
}

function aggregateDiffStats(outputText: string, files: ToolOutputFile[]): { added: number; removed: number } {
  const fromText = diffStatsFromText(outputText)
  if (fromText.added > 0 || fromText.removed > 0) {
    return fromText
  }
  let added = 0
  let removed = 0
  let any = false
  for (const file of files) {
    const parsed = parseStatsFromSummary(file.summary)
    if (parsed) {
      any = true
      added += parsed.added
      removed += parsed.removed
    }
  }
  if (any) {
    return { added, removed }
  }
  return { added: 0, removed: 0 }
}

function changeTypeLabel(changeType: ToolOutputFile['changeType']): string {
  if (changeType === 'created') {
    return 'CREATED'
  }
  if (changeType === 'deleted') {
    return 'DELETED'
  }
  return 'UPDATED'
}

const KEYWORD_RE =
  /\b(import|export|const|let|var|function|return|async|await|new|from|default|class|extends|interface|type)\b/g

function highlightCodeSegment(segment: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = []
  let last = 0
  const re = new RegExp(KEYWORD_RE.source, 'g')
  let match: RegExpExecArray | null
  while ((match = re.exec(segment)) !== null) {
    if (match.index > last) {
      nodes.push(
        <span key={`${keyPrefix}-plain-${last}`} className={styles.fileChangeTokPlain}>
          {segment.slice(last, match.index)}
        </span>,
      )
    }
    nodes.push(
      <span key={`${keyPrefix}-kw-${match.index}`} className={styles.fileChangeTokKeyword}>
        {match[1]}
      </span>,
    )
    last = match.index + match[0].length
  }
  if (last < segment.length) {
    nodes.push(
      <span key={`${keyPrefix}-plain-end`} className={styles.fileChangeTokPlain}>
        {segment.slice(last)}
      </span>,
    )
  }
  return nodes.length ? nodes : [<span key={`${keyPrefix}-empty`}>{segment}</span>]
}

function highlightCodeLine(line: string, lineKey: string): ReactNode {
  const parts = line.split(/('[^']*'|"[^"]*")/g)
  const out: ReactNode[] = []
  parts.forEach((part, index) => {
    if (/^['"]/.test(part)) {
      out.push(
        <span key={`${lineKey}-str-${index}`} className={styles.fileChangeTokString}>
          {part}
        </span>,
      )
    } else {
      out.push(...highlightCodeSegment(part, `${lineKey}-${index}`))
    }
  })
  return <>{out}</>
}

function diffLineDisplay(line: string): { gutter: string; body: string; rowClass: string } {
  if (line.startsWith('+++') || line.startsWith('---') || line.startsWith('@@')) {
    return { gutter: ' ', body: line, rowClass: styles.fileChangeDiffRowMeta }
  }
  if (line.startsWith('+') && !line.startsWith('+++')) {
    return { gutter: '+', body: line.slice(1), rowClass: styles.fileChangeDiffRowAdd }
  }
  if (line.startsWith('-') && !line.startsWith('---')) {
    return { gutter: '−', body: line.slice(1), rowClass: styles.fileChangeDiffRowDel }
  }
  return { gutter: ' ', body: line.startsWith(' ') ? line.slice(1) : line, rowClass: styles.fileChangeDiffRowCtx }
}

function IconFile() {
  return (
    <svg
      className={styles.fileChangeFileIcon}
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M14 2v6h6"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconCopy() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M8 8V5.2c0-1.12 0-1.68.22-2.11a2 2 0 0 1 .87-.87C9.52 2 10.08 2 11.2 2h5.6c1.12 0 1.68 0 2.11.22a2 2 0 0 1 .87.87C20 3.52 20 4.08 20 5.2v5.6c0 1.12 0 1.68-.22 2.11a2 2 0 0 1-.87.87C18.48 14 17.92 14 16.8 14H14M5.2 22h5.6c1.12 0 1.68 0 2.11-.22a2 2 0 0 0 .87-.87c.22-.43.22-.99.22-2.11v-5.6c0-1.12 0-1.68-.22-2.11a2 2 0 0 0-.87-.87C12.48 10 11.92 10 10.8 10H5.2c-1.12 0-1.68 0-2.11.22a2 2 0 0 0-.87.87C2 11.52 2 12.08 2 13.2v5.6c0 1.12 0 1.68.22 2.11.22.43.87.87.87.87 1.43.22 1.99.22Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconExpandVertical({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={expanded ? styles.fileChangeExpandIconOpen : ''}
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M12 5v14M8 9l4-4 4 4M8 15l4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconMore() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 13a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm0-8a1 1 0 1 0 0-2 1 1 0 0 0 0 2zm0 16a1 1 0 1 0 0-2 1 1 0 0 0 0 2z"
        fill="currentColor"
      />
    </svg>
  )
}

export function FileChangeToolRow({
  item,
  isExpanded = false,
  onToggle,
}: {
  item: ToolItem
  isExpanded?: boolean
  onToggle?: (itemId: string) => void
}) {
  const headline = getToolHeadline(item)
  const sourceText = useMemo(() => {
    const out = item.outputText.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    const args = item.argumentsText?.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim() ?? ''
    if (out.trim()) {
      return out
    }
    return args
  }, [item.argumentsText, item.outputText])

  const hasArguments = Boolean(item.argumentsText?.trim())
  const hasOutput = Boolean(item.outputText.trim())
  const hasFiles = item.outputFiles.length > 0
  const hasMeaningfulBody = hasMeaningfulToolContent(item)
  const canToggle = hasArguments || hasOutput || hasFiles
  const showBody = !canToggle || isExpanded

  const primaryFile = item.outputFiles[0]
  const fileName = useMemo(() => {
    if (item.outputFiles.length > 1) {
      return `${item.outputFiles.length} files`
    }
    if (primaryFile) {
      return basename(primaryFile.path)
    }
    const t = normalizeText(item.title)
    if (t && (t.includes('/') || t.includes('\\'))) {
      return basename(t)
    }
    return t || headline || 'File'
  }, [headline, item.outputFiles.length, item.title, primaryFile])

  const badgeLabel = primaryFile ? changeTypeLabel(primaryFile.changeType) : 'UPDATED'
  const stats = useMemo(() => aggregateDiffStats(sourceText, item.outputFiles), [item.outputFiles, sourceText])

  const lines = useMemo(() => {
    if (!sourceText.trim()) {
      return [] as string[]
    }
    return sourceText.split('\n')
  }, [sourceText])

  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!menuOpen) {
      return
    }
    const onDoc = (e: MouseEvent) => {
      if (!menuRef.current?.contains(e.target as Node)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [menuOpen])

  const copyDiff = useCallback(() => {
    const text = sourceText.trim() || normalizeText(item.argumentsText)
    if (text) {
      void navigator.clipboard.writeText(text)
    }
  }, [item.argumentsText, sourceText])

  const copyPath = useCallback(() => {
    const path = primaryFile?.path ?? ''
    if (path) {
      void navigator.clipboard.writeText(path)
    }
    setMenuOpen(false)
  }, [primaryFile?.path])

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-tool">
      <div className={`${styles.card} ${styles.fileChangeCard}`}>
        <header className={styles.fileChangeHeader}>
          <div className={styles.fileChangeHeaderMain}>
            <IconFile />
            <div className={styles.fileChangeHeaderText}>
              <span className={styles.fileChangeFileName}>{fileName}</span>
              <span className={styles.fileChangeBadge}>{badgeLabel}</span>
              <span className={styles.fileChangeSep} aria-hidden>
                |
              </span>
              <span className={styles.fileChangeStats}>
                <span className={styles.fileChangeStatAdd}>+{stats.added}</span>
                <span className={styles.fileChangeStatDel}>−{stats.removed}</span>
              </span>
            </div>
          </div>
          <div className={styles.fileChangeHeaderActions}>
            <button
              type="button"
              className={styles.fileChangeIconBtn}
              aria-label="Copy diff"
              onClick={copyDiff}
              disabled={!sourceText.trim() && !normalizeText(item.argumentsText)}
            >
              <IconCopy />
            </button>
            {canToggle ? (
              <button
                type="button"
                className={styles.fileChangeIconBtn}
                aria-expanded={showBody}
                aria-label={showBody ? 'Collapse diff' : 'Expand diff'}
                onClick={() => onToggle?.(item.id)}
              >
                <IconExpandVertical expanded={showBody} />
              </button>
            ) : null}
            <div className={styles.fileChangeMenuWrap} ref={menuRef}>
              <button
                type="button"
                className={styles.fileChangeIconBtn}
                aria-label="More actions"
                aria-expanded={menuOpen}
                onClick={() => setMenuOpen((open) => !open)}
                disabled={!primaryFile?.path}
              >
                <IconMore />
              </button>
              {menuOpen && primaryFile?.path ? (
                <div className={styles.fileChangeMenu} role="menu">
                  <button type="button" className={styles.fileChangeMenuItem} role="menuitem" onClick={copyPath}>
                    Copy file path
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        {showBody && lines.length > 0 ? (
          <div className={styles.fileChangeBody}>
            <div className={styles.fileChangeViewport}>
              {lines.map((line, index) => {
                const { gutter, body, rowClass } = diffLineDisplay(line)
                const isAdd = rowClass === styles.fileChangeDiffRowAdd
                const showSyntax = isAdd || rowClass === styles.fileChangeDiffRowCtx
                return (
                  <div key={`${index}-${line.slice(0, 24)}`} className={`${styles.fileChangeDiffRow} ${rowClass}`}>
                    <span className={styles.fileChangeLineNum}>{index + 1}</span>
                    <span className={styles.fileChangeGutter} aria-hidden>
                      {gutter}
                    </span>
                    <code className={styles.fileChangeCode}>
                      {showSyntax && body.trim() ? highlightCodeLine(body, `l-${index}`) : body || ' '}
                    </code>
                  </div>
                )
              })}
            </div>
          </div>
        ) : null}

        {showBody && lines.length === 0 && hasFiles ? (
          <div className={styles.fileChangeFileList}>
            {item.outputFiles.map((file) => (
              <div key={`${file.path}-${file.changeType}`} className={styles.fileChangeFileListRow}>
                <span className={styles.fileChangeMiniBadge}>{changeTypeLabel(file.changeType)}</span>
                <code className={styles.fileChangeFileListPath}>{file.path}</code>
                {file.summary ? <span className={styles.subtleText}>{file.summary}</span> : null}
              </div>
            ))}
          </div>
        ) : null}

        {showBody && !hasMeaningfulBody ? (
          <div className={styles.subtleText}>{getToolPlaceholderText(item)}</div>
        ) : null}
      </div>
    </article>
  )
}
