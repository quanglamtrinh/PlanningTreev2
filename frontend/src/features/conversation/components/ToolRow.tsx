import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { ItemStatus, ToolItem } from '../../../api/types'
import styles from './ConversationFeed.module.css'
import {
  inferFileWritesFromCommandText,
  inferInlineFileWriteContentFromCommandText,
  toAddedDiffText,
} from './fileChangeInference'
import { FileChangeToolRow } from './FileChangeToolRow'
import {
  getToolHeadline,
  getToolPlaceholderText,
  hasMeaningfulToolContent,
} from './toolPresentation'
import { MAX_COMMAND_OUTPUT_LINES } from './useConversationViewState'

function toolLabel(toolType: ToolItem['toolType']) {
  if (toolType === 'commandExecution') return 'Command'
  if (toolType === 'fileChange') return 'File Change'
  return 'Tool'
}

function formatCommandHeaderStatus(status: ItemStatus): string {
  switch (status) {
    case 'completed':
      return 'Completed'
    case 'in_progress':
      return 'Running'
    case 'failed':
      return 'Failed'
    case 'cancelled':
      return 'Cancelled'
    case 'pending':
      return 'Pending'
    case 'requested':
      return 'Requested'
    case 'answer_submitted':
      return 'Answer submitted'
    case 'answered':
      return 'Answered'
    case 'stale':
      return 'Stale'
    default:
      return String(status).replace(/_/g, ' ')
  }
}

function shellPrefixForCommand(commandLine: string): string {
  const c = commandLine.toLowerCase()
  if (
    c.includes('powershell') ||
    c.includes('pwsh') ||
    c.includes('.ps1') ||
    c.includes('cmd.exe')
  ) {
    return 'PS >'
  }
  return '$'
}

function IconCommandChevron({ expanded }: { expanded: boolean }) {
  return (
    <svg
      className={`${styles.commandChevron} ${expanded ? styles.commandChevronExpanded : ''}`}
      width="12"
      height="12"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M6 9l6 6 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function trailingCommandOutput(outputText: string): string {
  const normalized = outputText.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const lines = normalized.split('\n')
  if (lines.length <= MAX_COMMAND_OUTPUT_LINES) {
    return normalized
  }
  return lines.slice(-MAX_COMMAND_OUTPUT_LINES).join('\n')
}

function looksLikeDiffText(text: string): boolean {
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  return /^(?:\+\+\+|---|@@)/m.test(normalized) || /^[+-][^\r\n]*/m.test(normalized)
}

function CommandOutputViewport({
  itemId,
  outputText,
  onRequestAutoScroll,
}: {
  itemId: string
  outputText: string
  onRequestAutoScroll?: () => void
}) {
  const viewportRef = useRef<HTMLDivElement | null>(null)
  const pinnedRef = useRef(true)
  const [, setPinnedVersion] = useState(0)

  const visibleOutput = useMemo(() => trailingCommandOutput(outputText), [outputText])

  const updatePinnedState = useCallback(() => {
    const viewport = viewportRef.current
    if (!viewport) {
      return
    }
    const isPinned = viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <= 8
    pinnedRef.current = isPinned
    setPinnedVersion((current) => current + 1)
  }, [])

  useLayoutEffect(() => {
    const viewport = viewportRef.current
    if (!viewport || !pinnedRef.current) {
      return
    }
    viewport.scrollTop = viewport.scrollHeight
    onRequestAutoScroll?.()
  }, [onRequestAutoScroll, visibleOutput])

  return (
    <div
      ref={viewportRef}
      className={styles.commandViewport}
      data-testid={`conversation-tool-output-${itemId}`}
      onScroll={updatePinnedState}
    >
      <pre className={styles.commandPre}>{visibleOutput}</pre>
    </div>
  )
}

function CommandExecutionToolRow({
  item,
  isExpanded,
  onToggle,
  onRequestAutoScroll,
}: {
  item: ToolItem
  isExpanded: boolean
  onToggle?: (itemId: string) => void
  onRequestAutoScroll?: () => void
}) {
  const headline = getToolHeadline(item)
  const hasArguments = Boolean(item.argumentsText?.trim())
  const hasOutput = Boolean(item.outputText.trim())
  const hasFiles = item.outputFiles.length > 0
  const hasMeaningfulBody = hasMeaningfulToolContent(item)
  const canToggle = hasArguments || hasOutput || hasFiles
  const showBody = !canToggle || isExpanded
  const prefix = shellPrefixForCommand(headline)

  const exitPill = (() => {
    if (item.exitCode !== null) {
      const ok = item.exitCode === 0
      return (
        <span
          className={`${styles.exitPill} ${ok ? styles.exitPillSuccess : styles.exitPillFailure}`}
        >
          <span className={styles.exitPillDot} aria-hidden />
          exit {item.exitCode}
        </span>
      )
    }
    if (item.status === 'in_progress') {
      return (
        <span className={`${styles.exitPill} ${styles.exitPillRunning}`}>
          <span className={styles.exitPillDot} aria-hidden />
          Running
        </span>
      )
    }
    if (item.status === 'failed' || item.status === 'cancelled') {
      const label = item.status === 'failed' ? 'Failed' : 'Cancelled'
      return (
        <span className={`${styles.exitPill} ${styles.exitPillFailure}`}>
          <span className={styles.exitPillDot} aria-hidden />
          {label}
        </span>
      )
    }
    return (
      <span className={`${styles.exitPill} ${styles.exitPillMuted}`}>
        <span className={styles.exitPillDot} aria-hidden />
        exit —
      </span>
    )
  })()

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-tool">
      <div className={`${styles.card} ${styles.commandCard}`}>
        <header className={styles.commandCardHeader}>
          <div className={styles.commandCardHeaderLeft}>
            <span className={styles.commandCardEyebrow}>Command</span>
            <span className={styles.commandHeaderStatusPill}>
              {formatCommandHeaderStatus(item.status)}
            </span>
          </div>
          {canToggle ? (
            <button
              type="button"
              className={styles.commandExpandToggle}
              onClick={() => onToggle?.(item.id)}
              aria-expanded={showBody}
            >
              {showBody ? 'Collapse' : 'Expand'}
              <IconCommandChevron expanded={showBody} />
            </button>
          ) : null}
        </header>

        <div className={styles.commandLineBar}>
          <span className={styles.commandPrompt}>{prefix}</span>
          {headline}
        </div>

        <div className={styles.commandOutputHeader}>
          <span className={styles.commandOutputEyebrow}>Output</span>
          {exitPill}
        </div>

        {showBody && hasOutput ? (
          <CommandOutputViewport
            itemId={item.id}
            outputText={item.outputText}
            onRequestAutoScroll={onRequestAutoScroll}
          />
        ) : null}

        {showBody && hasFiles ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Files</div>
            <div className={styles.fileList}>
              {item.outputFiles.map((file) => (
                <div key={`${file.path}-${file.changeType}`} className={styles.fileItem}>
                  <div className={styles.fileMeta}>
                    <span className={styles.statusPill}>{file.changeType}</span>
                    <code>{file.path}</code>
                  </div>
                  {file.summary ? <div className={styles.subtleText}>{file.summary}</div> : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {showBody && !hasMeaningfulBody ? (
          <div className={styles.subtleText}>{getToolPlaceholderText(item)}</div>
        ) : null}
      </div>
    </article>
  )
}

export function ToolRow({
  item,
  isExpanded = false,
  onToggle,
  onRequestAutoScroll,
}: {
  item: ToolItem
  isExpanded?: boolean
  onToggle?: (itemId: string) => void
  onRequestAutoScroll?: () => void
}) {
  const inferenceSource = [item.argumentsText, item.title, item.toolName, item.outputText]
    .map((part) => String(part ?? '').trim())
    .filter(Boolean)
    .join('\n')
  const inferredFiles = inferFileWritesFromCommandText(inferenceSource)
  const inferredContent = inferInlineFileWriteContentFromCommandText(inferenceSource)
  const effectiveFileOutputs = item.outputFiles.length
    ? item.outputFiles
    : inferredFiles.map((file) => ({
        path: file.path,
        changeType: file.changeType,
        summary: file.summary,
      }))
  const normalizedOutputText = item.outputText.trim()
  const effectiveOutputText =
    inferredContent
      ? toAddedDiffText(inferredContent)
      : normalizedOutputText.length > 0
        ? item.toolType === 'commandExecution' &&
          effectiveFileOutputs.length > 0 &&
          !looksLikeDiffText(item.outputText)
          ? toAddedDiffText(item.outputText)
          : item.outputText
        : item.outputText

  if (item.toolType === 'fileChange' || effectiveFileOutputs.length > 0) {
    return (
      <FileChangeToolRow
        item={{
          ...item,
          toolType: 'fileChange',
          outputText: effectiveOutputText,
          outputFiles: effectiveFileOutputs,
        }}
        isExpanded={isExpanded}
        onToggle={onToggle}
      />
    )
  }

  if (item.toolType === 'commandExecution') {
    return (
      <CommandExecutionToolRow
        item={item}
        isExpanded={isExpanded}
        onToggle={onToggle}
        onRequestAutoScroll={onRequestAutoScroll}
      />
    )
  }

  const headline = getToolHeadline(item)
  const hasArguments = Boolean(item.argumentsText?.trim())
  const hasOutput = Boolean(item.outputText.trim())
  const hasFiles = item.outputFiles.length > 0
  const hasMeaningfulBody = hasMeaningfulToolContent(item)
  const canToggle = hasArguments || hasOutput || hasFiles
  const showBody = !canToggle || isExpanded

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-tool">
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>{toolLabel(item.toolType)}</div>
            <div className={styles.cardTitleRow}>
              <h3 className={styles.cardTitle}>{headline}</h3>
              {canToggle ? (
                <button
                  type="button"
                  className={styles.inlineToggle}
                  onClick={() => onToggle?.(item.id)}
                >
                  {showBody ? 'Collapse' : 'Expand'}
                </button>
              ) : null}
            </div>
          </div>
          <div className={styles.cardMeta}>
            <span className={styles.statusPill}>{item.status}</span>
            {item.toolName ? <span>{item.toolName}</span> : null}
            {item.exitCode != null ? <span>exit {item.exitCode}</span> : null}
          </div>
        </div>

        {showBody && hasArguments ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Arguments</div>
            <pre className={styles.plainPre}>{item.argumentsText}</pre>
          </div>
        ) : null}

        {showBody && hasOutput ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Output</div>
            <pre className={styles.plainPre}>{item.outputText}</pre>
          </div>
        ) : null}

        {showBody && hasFiles ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Files</div>
            <div className={styles.fileList}>
              {item.outputFiles.map((file) => (
                <div key={`${file.path}-${file.changeType}`} className={styles.fileItem}>
                  <div className={styles.fileMeta}>
                    <span className={styles.statusPill}>{file.changeType}</span>
                    <code>{file.path}</code>
                  </div>
                  {file.summary ? <div className={styles.subtleText}>{file.summary}</div> : null}
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {showBody && !hasMeaningfulBody ? (
          <div className={styles.subtleText}>{getToolPlaceholderText(item)}</div>
        ) : null}
      </div>
    </article>
  )
}
