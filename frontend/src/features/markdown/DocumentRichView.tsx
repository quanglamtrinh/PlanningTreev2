import type { ReactNode } from 'react'
import { SharedMarkdownRenderer } from './SharedMarkdownRenderer'
import styles from './DocumentRichView.module.css'

type DocumentRichViewContentProps = {
  content: string
  projectRootPath?: string
  emptyMessage?: string
  testId?: string
  className?: string
}

type DocumentRichViewPanelProps = DocumentRichViewContentProps & {
  fileLabel?: string
  title?: string
  headerActions?: ReactNode
}

export function DocumentRichViewContent({
  content,
  projectRootPath,
  emptyMessage = 'No content yet.',
  testId,
  className,
}: DocumentRichViewContentProps) {
  const rootClassName = className
    ? `${styles.richViewSurface} ${className}`
    : styles.richViewSurface

  return (
    <div className={rootClassName} data-testid={testId}>
      {content.trim() ? (
        <SharedMarkdownRenderer
          content={content}
          projectRootPath={projectRootPath}
          variant="document"
        />
      ) : (
        <p className={styles.richViewEmpty}>{emptyMessage}</p>
      )}
    </div>
  )
}

export function DocumentRichViewPanel({
  content,
  projectRootPath,
  emptyMessage,
  testId,
  fileLabel,
  title = 'Markdown editor',
  headerActions,
}: DocumentRichViewPanelProps) {
  return (
    <div className={styles.documentPanel}>
      {fileLabel ? <div className={styles.documentFileLabel}>{fileLabel}</div> : null}
      <div className={styles.editorSurface}>
        <div className={styles.editorSurfaceHeader}>
          <div className={styles.editorSurfaceHeaderMain}>
            <span className={styles.editorSurfaceTitle}>{title}</span>
            <div className={styles.editorModeToggle} role="group" aria-label={`${fileLabel ?? 'document'} view mode`}>
              <span className={styles.editorModeToggleButton}>Edit</span>
              <span className={`${styles.editorModeToggleButton} ${styles.editorModeToggleButtonActive}`}>
                Rich View
              </span>
            </div>
          </div>
          {headerActions ? <div className={styles.editorSurfaceHeaderActions}>{headerActions}</div> : null}
        </div>
        <div className={styles.editorSurfaceBody}>
          <DocumentRichViewContent
            content={content}
            projectRootPath={projectRootPath}
            emptyMessage={emptyMessage}
            testId={testId}
          />
        </div>
      </div>
    </div>
  )
}