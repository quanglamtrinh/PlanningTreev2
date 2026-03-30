import { useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { ToolItem } from '../../../api/types'
import styles from './ConversationFeed.module.css'
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

function trailingCommandOutput(outputText: string): string {
  const normalized = outputText.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
  const lines = normalized.split('\n')
  if (lines.length <= MAX_COMMAND_OUTPUT_LINES) {
    return normalized
  }
  return lines.slice(-MAX_COMMAND_OUTPUT_LINES).join('\n')
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

        {showBody && hasOutput && item.toolType === 'commandExecution' ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Output</div>
            <CommandOutputViewport
              itemId={item.id}
              outputText={item.outputText}
              onRequestAutoScroll={onRequestAutoScroll}
            />
          </div>
        ) : null}

        {showBody && hasOutput && item.toolType !== 'commandExecution' ? (
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
