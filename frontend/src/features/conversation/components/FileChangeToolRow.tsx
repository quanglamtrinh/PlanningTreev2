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

function fileRowKey(file: ToolOutputFile): string {
  return `${file.path}\u0000${file.changeType}`
}

const STRUCTURED_DIFF_MARKER_RE =
  /^(?:diff --git |\+\+\+|---|@@ |\*\*\* Begin Patch|\*\*\* Update File:|\*\*\* Add File:|\*\*\* Delete File:|\*\*\* Move to:)/m

function hasStructuredDiffMarkers(text: string): boolean {
  return STRUCTURED_DIFF_MARKER_RE.test(text.replace(/\r\n/g, '\n').replace(/\r/g, '\n'))
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
  const s = summary.trim()
  const minus = '[\\-\\u2212]'
  const pairLoose = new RegExp(`\\+(\\d+)\\s*${minus}\\s*(\\d+)`)
  const mLoose = s.match(pairLoose)
  if (mLoose) {
    return { added: Number(mLoose[1]), removed: Number(mLoose[2]) }
  }
  const mLegacy = s.match(/\+\s*(\d+)[^\d-]*-\s*(\d+)/)
  if (mLegacy) {
    return { added: Number(mLegacy[1]), removed: Number(mLegacy[2]) }
  }
  const ins = s.match(/(\d+)\s+insertions?\b/i)
  const dels = s.match(/(\d+)\s+deletions?\b/i)
  if (ins || dels) {
    return {
      added: ins ? Number(ins[1]) : 0,
      removed: dels ? Number(dels[1]) : 0,
    }
  }
  return null
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

function normalizePathForMatch(p: string): string {
  return p
    .replace(/\\/g, '/')
    .replace(/^\.\/+/, '')
    .replace(/^\/+/, '')
    .toLowerCase()
}

function stripGitABPrefix(segment: string): string {
  let s = segment.trim()
  if ((s.startsWith('a/') || s.startsWith('b/')) && s.length > 2) {
    s = s.slice(2)
  }
  return s.replace(/\\/g, '/')
}

/** Paths from `diff --git a/x b/y` (supports quoted segments). */
function extractPathsFromDiffGitLine(line: string): string[] {
  const payload = line.slice('diff --git '.length).trimEnd()
  if (!payload) {
    return []
  }
  const paths: string[] = []
  let rest = payload
  while (rest.length > 0) {
    if (rest[0] === '"') {
      const end = rest.indexOf('"', 1)
      if (end < 0) {
        break
      }
      const raw = rest.slice(1, end)
      paths.push(stripGitABPrefix(raw))
      rest = rest.slice(end + 1).trimStart()
    } else {
      const sp = rest.indexOf(' ')
      const token = sp >= 0 ? rest.slice(0, sp) : rest
      paths.push(stripGitABPrefix(token))
      rest = sp >= 0 ? rest.slice(sp + 1).trimStart() : ''
    }
  }
  return paths.filter(Boolean)
}

function isApplyPatchFileHeader(line: string): boolean {
  return (
    line.startsWith('*** Update File: ') ||
    line.startsWith('*** Add File: ') ||
    line.startsWith('*** Delete File: ')
  )
}

function extractApplyPatchPath(line: string): string | null {
  const match = line.match(/^\*\*\*\s+(?:Update File|Add File|Delete File|Move to):\s+(.+)$/)
  if (!match?.[1]) {
    return null
  }
  const raw = stripGitABPrefix(match[1].trim())
  return raw || null
}

type UnifiedDiffChunk = {
  relPaths: string[]
  added: number
  removed: number
  /** Inclusive start index in split lines (the `diff --git` line). */
  startLine: number
  /** Exclusive end index (first line after this hunk). */
  endLine: number
}

/** Split unified diff into one record per `diff --git` hunk. */
function parseUnifiedDiffChunks(outputText: string): UnifiedDiffChunk[] {
  const trimmed = outputText.replace(/\r\n/g, '\n')
  if (!trimmed.trim()) {
    return []
  }
  const lines = trimmed.split('\n')
  const chunks: UnifiedDiffChunk[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith('diff --git ')) {
      const startLine = i
      const relPaths = extractPathsFromDiffGitLine(line)
      i += 1
      let added = 0
      let removed = 0
      while (i < lines.length && !lines[i].startsWith('diff --git ') && !isApplyPatchFileHeader(lines[i])) {
        const L = lines[i]
        if (L.startsWith('+') && !L.startsWith('+++')) {
          added += 1
        } else if (L.startsWith('-') && !L.startsWith('---')) {
          removed += 1
        }
        i += 1
      }
      const endLine = i
      chunks.push({ relPaths, added, removed, startLine, endLine })
      continue
    }
    if (isApplyPatchFileHeader(line)) {
      const startLine = i
      const relPaths: string[] = []
      const headerPath = extractApplyPatchPath(line)
      if (headerPath) {
        relPaths.push(headerPath)
      }
      i += 1
      let added = 0
      let removed = 0
      while (i < lines.length && !lines[i].startsWith('diff --git ') && !isApplyPatchFileHeader(lines[i])) {
        const L = lines[i]
        if (L.startsWith('*** End Patch')) {
          break
        }
        if (L.startsWith('*** Move to: ')) {
          const movePath = extractApplyPatchPath(L)
          if (movePath) {
            relPaths.push(movePath)
          }
          i += 1
          continue
        }
        if (L.startsWith('+') && !L.startsWith('+++')) {
          added += 1
        } else if (L.startsWith('-') && !L.startsWith('---')) {
          removed += 1
        }
        i += 1
      }
      const endLine = i
      chunks.push({ relPaths, added, removed, startLine, endLine })
      continue
    }
    if (line.startsWith('*** End Patch')) {
      i += 1
      continue
    }
    i += 1
  }
  return chunks
}

function scorePathAgainstChunk(relPaths: readonly string[], fileNorm: string): number {
  const fileBase = basename(fileNorm).toLowerCase()
  let best = 0
  for (const rp of relPaths) {
    const pn = normalizePathForMatch(rp)
    if (!pn) {
      continue
    }
    if (pn === fileNorm) {
      return 10000 + pn.length
    }
    if (fileNorm === pn || fileNorm.endsWith(`/${pn}`) || fileNorm.endsWith(pn)) {
      best = Math.max(best, 5000 + pn.length)
    } else if (pn.endsWith(`/${fileNorm}`) || fileNorm.includes(`/${pn}/`) || pn.includes(`/${fileNorm}/`)) {
      best = Math.max(best, 2000 + Math.min(pn.length, fileNorm.length))
    } else {
      const chunkBase = basename(pn).toLowerCase()
      if (chunkBase && chunkBase === fileBase) {
        best = Math.max(best, 500 + pn.length)
      }
    }
  }
  return best
}

function findBestChunkForPath(
  chunks: readonly UnifiedDiffChunk[],
  filePath: string,
): UnifiedDiffChunk | null {
  const fileNorm = normalizePathForMatch(filePath)
  if (!fileNorm) {
    return null
  }
  let bestChunk: UnifiedDiffChunk | null = null
  let bestScore = 0
  for (const ch of chunks) {
    const sc = scorePathAgainstChunk(ch.relPaths, fileNorm)
    if (sc > bestScore) {
      bestScore = sc
      bestChunk = ch
    }
  }
  if (!bestChunk || bestScore < 500) {
    return null
  }
  return bestChunk
}

function fallbackChunkByOrder(chunks: readonly UnifiedDiffChunk[], fileIndex: number): UnifiedDiffChunk | null {
  if (chunks.length === 0) {
    return null
  }
  if (fileIndex >= 0 && fileIndex < chunks.length) {
    return chunks[fileIndex]
  }
  if (chunks.length === 1) {
    return chunks[0]
  }
  return null
}

function resolveChunkForFile(
  chunks: readonly UnifiedDiffChunk[],
  filePath: string,
  fileIndex: number,
): UnifiedDiffChunk | null {
  return findBestChunkForPath(chunks, filePath) ?? fallbackChunkByOrder(chunks, fileIndex)
}

function statsFromChunksForPath(chunks: readonly UnifiedDiffChunk[], filePath: string): { added: number; removed: number } | null {
  const ch = findBestChunkForPath(chunks, filePath)
  return ch ? { added: ch.added, removed: ch.removed } : null
}

function resolvedStatsForFile(
  file: ToolOutputFile,
  chunks: readonly UnifiedDiffChunk[],
  outputText: string,
  allowSingleBlobFallback: boolean,
  fallbackChunk?: UnifiedDiffChunk | null,
): { added: number; removed: number } {
  const parsed = parseStatsFromSummary(file.summary)
  if (parsed) {
    return parsed
  }
  const fromUnified = statsFromChunksForPath(chunks, file.path)
  if (fromUnified) {
    return fromUnified
  }
  if (fallbackChunk) {
    return { added: fallbackChunk.added, removed: fallbackChunk.removed }
  }
  const trimmed = outputText.replace(/\r\n/g, '\n').trim()
  if (
    allowSingleBlobFallback &&
    trimmed &&
    chunks.length === 0 &&
    (file.changeType === 'updated' || file.changeType === 'created')
  ) {
    const singleFileGuess = diffStatsFromText(trimmed)
    if (singleFileGuess.added > 0 || singleFileGuess.removed > 0) {
      return singleFileGuess
    }
  }
  if (file.changeType === 'created') {
    return { added: 1, removed: 0 }
  }
  if (file.changeType === 'deleted') {
    return { added: 0, removed: 1 }
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
    return { gutter: '-', body: line.slice(1), rowClass: styles.fileChangeDiffRowDel }
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
        d="M8 8V5.2c0-1.12 0-1.68.22-2.11a2 2 0 0 1 .87-.87C9.52 2 10.08 2 11.2 2h5.6c1.12 0 1.68 0 2.11.22a2 2 0 0 1 .87.87C20 3.52 20 4.08 20 5.2v5.6c0 1.12 0 1.68-.22 2.11a2 2 0 0 1-.87.87C18.48 14 17.92 14 16.8 14H14M5.2 22h5.6c1.12 0 1.68 0 2.11-.22a2 2 0 0 0 .87-.87c.22-.43.22-.99.22-2.11v-5.6c0-1.12 0-1.68-.22-2.11a2 2 0 0 0-.87-.87C12.48 10 11.92 10 10.8 10H5.2c-1.12 0-1.68 0-2.11.22a2 2 0 0 0-.87.87C2 11.52 2 12.08 2 13.2v5.6c0 1.12 0 1.68.22 2.11a2 2 0 0 0 .87.87c.43.22.99.22 2.11.22Z"
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

function IconChevronDown({ open }: { open: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
      className={`${styles.fileChangeRowChevron} ${open ? styles.fileChangeRowChevronOpen : ''}`}
    >
      <path
        d="M7 10l5 5 5-5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function FileChangeToolRow({
  item,
  isExpanded = false,
  onToggle,
  dataTestId = 'conversation-item-tool',
}: {
  item: ToolItem
  isExpanded?: boolean
  onToggle?: (itemId: string) => void
  dataTestId?: string
}) {
  const headline = getToolHeadline(item)
  const sourceText = useMemo(() => {
    const out = item.outputText.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    const args = item.argumentsText?.replace(/\r\n/g, '\n').replace(/\r/g, '\n') ?? ''
    if (hasStructuredDiffMarkers(out)) {
      return out
    }
    if (hasStructuredDiffMarkers(args)) {
      return args
    }
    if (out.trim()) {
      return out
    }
    return args.trim() ? args : ''
  }, [item.argumentsText, item.outputText])

  const hasArguments = Boolean(item.argumentsText?.trim())
  const hasOutput = Boolean(item.outputText.trim())
  const hasFiles = item.outputFiles.length > 0
  const hasMeaningfulBody = hasMeaningfulToolContent(item)
  const canToggle = hasArguments || hasOutput || hasFiles
  const showBody = !canToggle || isExpanded

  const primaryFile = item.outputFiles[0]
  const isMultiFile = item.outputFiles.length > 1
  const diffChunks = useMemo(() => parseUnifiedDiffChunks(sourceText), [sourceText])
  const multiFileRows = useMemo(
    () =>
      item.outputFiles.map((file, index) => {
        const chunk = resolveChunkForFile(diffChunks, file.path, index)
        return {
          file,
          chunk,
          ...resolvedStatsForFile(file, diffChunks, sourceText, item.outputFiles.length <= 1, chunk),
        }
      }),
    [diffChunks, item.outputFiles, sourceText],
  )

  const fileName = useMemo(() => {
    if (isMultiFile) {
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
  }, [headline, isMultiFile, item.outputFiles.length, item.title, primaryFile])

  const badgeLabel = primaryFile ? changeTypeLabel(primaryFile.changeType) : 'UPDATED'
  const stats = useMemo(() => aggregateDiffStats(sourceText, item.outputFiles), [item.outputFiles, sourceText])

  const lines = useMemo(() => {
    if (!sourceText.trim()) {
      return [] as string[]
    }
    return sourceText.split('\n')
  }, [sourceText])

  const [menuOpen, setMenuOpen] = useState(false)
  const [expandedMultiKey, setExpandedMultiKey] = useState<string | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    setExpandedMultiKey(null)
  }, [item.id])

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

  const copyAllPaths = useCallback(() => {
    const text = item.outputFiles.map((f) => f.path).join('\n')
    if (text.trim()) {
      void navigator.clipboard.writeText(text)
    }
    setMenuOpen(false)
  }, [item.outputFiles])

  const multiFileLabel = `${item.outputFiles.length} files changed`

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid={dataTestId}>
      <div
        className={`${styles.card} ${styles.fileChangeCard} ${isMultiFile ? styles.fileChangeMultiCard : ''}`}
      >
        {isMultiFile ? (
          <>
            <header className={`${styles.fileChangeHeader} ${styles.fileChangeMultiHeader}`}>
              <div className={styles.fileChangeMultiTitleRow}>
                <span className={styles.fileChangeMultiTitle}>{multiFileLabel}</span>
                <span className={styles.fileChangeStats}>
                  <span className={styles.fileChangeStatAdd}>+{stats.added}</span>
                  <span className={styles.fileChangeStatDel}>-{stats.removed}</span>
                </span>
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
                <div className={styles.fileChangeMenuWrap} ref={menuRef}>
                  <button
                    type="button"
                    className={styles.fileChangeIconBtn}
                    aria-label="More actions"
                    aria-expanded={menuOpen}
                    onClick={() => setMenuOpen((open) => !open)}
                  >
                    <IconMore />
                  </button>
                  {menuOpen ? (
                    <div className={styles.fileChangeMenu} role="menu">
                      {primaryFile?.path ? (
                        <button
                          type="button"
                          className={styles.fileChangeMenuItem}
                          role="menuitem"
                          onClick={copyPath}
                        >
                          Copy file path
                        </button>
                      ) : null}
                      <button
                        type="button"
                        className={styles.fileChangeMenuItem}
                        role="menuitem"
                        onClick={copyAllPaths}
                      >
                        Copy all paths
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            </header>
            <ul className={styles.fileChangeMultiList} aria-label="Changed files">
              {multiFileRows.map(({ file, added, removed, chunk }) => {
                const rowKey = fileRowKey(file)
                const rowOpen = expandedMultiKey === rowKey
                const rowLines =
                  chunk != null
                    ? lines.slice(chunk.startLine, chunk.endLine)
                    : diffChunks.length === 0 && lines.length > 0
                      ? lines
                      : []
                const displayName = basename(file.path)
                return (
                  <li key={rowKey} className={styles.fileChangeMultiItem}>
                    <div className={styles.fileChangeMultiRow}>
                      <div className={styles.fileChangeMultiLeft}>
                        <span className={styles.fileChangeMultiPath} title={file.path}>
                          {displayName}
                        </span>
                        <span className={styles.fileChangeMultiRowStats}>
                          <span className={styles.fileChangeStatAdd}>+{added}</span>
                          <span className={styles.fileChangeStatDel}>-{removed}</span>
                        </span>
                      </div>
                      <button
                        type="button"
                        className={styles.fileChangeMultiChevronBtn}
                        aria-expanded={rowOpen}
                        aria-label={rowOpen ? `Collapse diff for ${displayName}` : `Expand diff for ${displayName}`}
                        onClick={() =>
                          setExpandedMultiKey((current) => (current === rowKey ? null : rowKey))
                        }
                      >
                        <IconChevronDown open={rowOpen} />
                      </button>
                    </div>
                    {rowOpen ? (
                      <div className={styles.fileChangeMultiRowPanel}>
                        {rowLines.length > 0 ? (
                          <div className={styles.fileChangeViewport}>
                            {rowLines.map((diffLine, index) => {
                              const { gutter, body, rowClass } = diffLineDisplay(diffLine)
                              const isAdd = rowClass === styles.fileChangeDiffRowAdd
                              const showSyntax = isAdd || rowClass === styles.fileChangeDiffRowCtx
                              return (
                                <div
                                  key={`${rowKey}-${index}-${diffLine.slice(0, 20)}`}
                                  className={`${styles.fileChangeDiffRow} ${rowClass}`}
                                >
                                  <span className={styles.fileChangeLineNum}>{index + 1}</span>
                                  <span className={styles.fileChangeGutter} aria-hidden>
                                    {gutter}
                                  </span>
                                  <code className={styles.fileChangeCode}>
                                    {showSyntax && body.trim()
                                      ? highlightCodeLine(body, `m-${rowKey}-${index}`)
                                      : body || ' '}
                                  </code>
                                </div>
                              )
                            })}
                          </div>
                        ) : (
                          <div className={styles.subtleText}>No diff excerpt for this file.</div>
                        )}
                      </div>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          </>
        ) : (
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
                  <span className={styles.fileChangeStatDel}>-{stats.removed}</span>
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
        )}

        {showBody && !isMultiFile && lines.length > 0 ? (
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

        {showBody && lines.length === 0 && hasFiles && !isMultiFile ? (
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

        {showBody && !isMultiFile && !hasMeaningfulBody ? (
          <div className={styles.subtleText}>{getToolPlaceholderText(item)}</div>
        ) : null}
      </div>
    </article>
  )
}
