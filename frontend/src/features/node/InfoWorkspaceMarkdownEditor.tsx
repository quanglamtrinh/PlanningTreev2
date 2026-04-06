import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { EditorView } from '@codemirror/view'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../../api/client'
import { vscodeMarkdownSyntaxHighlighting } from './codemirror/vscodeMarkdownHighlight'
import styles from './NodeDetailCard.module.css'

const SAVE_DEBOUNCE_MS = 800

type Props = {
  projectId: string
  /** Path under project workspace root (API). */
  workspaceRelativePath: string
  /** Label shown in toolbar (list path). */
  displayPath: string
  onClose: () => void
}

export function InfoWorkspaceMarkdownEditor({
  projectId,
  workspaceRelativePath,
  displayPath,
  onClose,
}: Props) {
  const [content, setContent] = useState('')
  const [savedContent, setSavedContent] = useState('')
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const editorSurfaceRef = useRef<HTMLDivElement>(null)
  const saveTimerRef = useRef<ReturnType<typeof globalThis.setTimeout> | undefined>(undefined)
  const syncRef = useRef({ content: '', savedContent: '' })
  syncRef.current = { content, savedContent }

  const flushSave = useCallback(async () => {
    const { content: draft, savedContent: saved } = syncRef.current
    if (draft === saved) {
      return
    }
    setIsSaving(true)
    setSaveError(null)
    try {
      const doc = await api.putWorkspaceTextFile(projectId, workspaceRelativePath, draft)
      setSavedContent(doc.content)
      syncRef.current = { content: doc.content, savedContent: doc.content }
    } catch (e) {
      setSaveError(e instanceof ApiError ? e.message : 'Save failed')
    } finally {
      setIsSaving(false)
    }
  }, [projectId, workspaceRelativePath])

  const scheduleSave = useCallback(() => {
    if (saveTimerRef.current !== undefined) {
      globalThis.clearTimeout(saveTimerRef.current)
    }
    saveTimerRef.current = globalThis.setTimeout(() => {
      saveTimerRef.current = undefined
      void flushSave()
    }, SAVE_DEBOUNCE_MS)
  }, [flushSave])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setLoadError(null)
    void api
      .getWorkspaceTextFile(projectId, workspaceRelativePath)
      .then((doc) => {
        if (cancelled) {
          return
        }
        setContent(doc.content)
        setSavedContent(doc.content)
        syncRef.current = { content: doc.content, savedContent: doc.content }
      })
      .catch((e) => {
        if (cancelled) {
          return
        }
        setLoadError(e instanceof ApiError ? e.message : 'Failed to load file')
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false)
        }
      })
    return () => {
      cancelled = true
    }
  }, [projectId, workspaceRelativePath])

  useEffect(() => {
    return () => {
      if (saveTimerRef.current !== undefined) {
        globalThis.clearTimeout(saveTimerRef.current)
      }
    }
  }, [])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content)
    } catch {
      /* clipboard may be unavailable */
    }
  }, [content])

  const handleEditorFullscreen = useCallback(() => {
    const el = editorSurfaceRef.current
    if (!el) {
      return
    }
    if (document.fullscreenElement === el) {
      void document.exitFullscreen()
    } else {
      void el.requestFullscreen().catch(() => undefined)
    }
  }, [])

  const isReadOnly = loading || Boolean(loadError)

  return (
    <div className={`${styles.describeInfoEditorHost} ${styles.documentPanel}`}>
      <div className={styles.infoWorkspaceEditorToolbar}>
        <button type="button" className={styles.describeWorkspaceButtonOutline} onClick={onClose}>
          ← Back to info
        </button>
        <div className={styles.documentFileLabelCell}>
          <span className={styles.documentFileLabelIcon} aria-hidden="true">
            <svg
              viewBox="0 0 16 16"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              width="13"
              height="13"
            >
              <path d="M4 2h6l3 3v9a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z" />
              <path d="M10 2v4h3" />
            </svg>
          </span>
          <span className={styles.documentFileLabel}>{displayPath}</span>
          {isSaving ? (
            <span className={styles.infoWorkspaceSaving} aria-live="polite">
              Saving…
            </span>
          ) : null}
        </div>
      </div>

      {loadError ? (
        <div className={styles.documentErrorPanel} role="alert">
          <p className={styles.body}>{loadError}</p>
          <button
            type="button"
            className={styles.retryButton}
            onClick={() => {
              setLoadError(null)
              setLoading(true)
              void api
                .getWorkspaceTextFile(projectId, workspaceRelativePath)
                .then((doc) => {
                  setContent(doc.content)
                  setSavedContent(doc.content)
                  syncRef.current = { content: doc.content, savedContent: doc.content }
                })
                .catch((e) => {
                  setLoadError(e instanceof ApiError ? e.message : 'Failed to load file')
                })
                .finally(() => {
                  setLoading(false)
                })
            }}
          >
            Retry
          </button>
        </div>
      ) : null}

      {saveError ? (
        <div className={styles.documentErrorPanel} role="alert">
          <p className={styles.body}>{saveError}</p>
        </div>
      ) : null}

      <div
        ref={editorSurfaceRef}
        className={styles.editorSurface}
        aria-busy={loading}
      >
        <div className={styles.editorSurfaceHeader}>
          <span className={styles.editorSurfaceTitle}>Markdown editor</span>
          <div className={styles.editorSurfaceHeaderActions}>
            <button
              type="button"
              className={styles.editorSurfaceHeaderIcon}
              onClick={() => {
                void handleCopy()
              }}
              aria-label="Copy document to clipboard"
            >
              <svg
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.35"
                strokeLinecap="round"
                strokeLinejoin="round"
                width="16"
                height="16"
                aria-hidden="true"
              >
                <rect x="5.5" y="5.5" width="8" height="8" rx="1" />
                <path d="M3.5 10.5h-1a1 1 0 01-1-1v-7a1 1 0 011-1h7a1 1 0 011 1v1" />
              </svg>
            </button>
            <button
              type="button"
              className={styles.editorSurfaceHeaderIcon}
              onClick={handleEditorFullscreen}
              aria-label="Toggle fullscreen editor"
            >
              <svg
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.35"
                strokeLinecap="round"
                strokeLinejoin="round"
                width="16"
                height="16"
                aria-hidden="true"
              >
                <path d="M10 2h4v4M6 2H2v4M2 10v4h4M10 14h4v-4" />
              </svg>
            </button>
          </div>
        </div>
        <div className={styles.editorSurfaceBody}>
          <CodeMirror
            className={styles.codemirrorHost}
            value={content}
            height="100%"
            theme="none"
            extensions={[markdown(), vscodeMarkdownSyntaxHighlighting, EditorView.lineWrapping]}
            basicSetup={{
              foldGutter: false,
              lineNumbers: true,
            }}
            editable={!isReadOnly}
            onChange={(value) => {
              setContent(value)
              scheduleSave()
            }}
            onBlur={() => {
              if (saveTimerRef.current !== undefined) {
                globalThis.clearTimeout(saveTimerRef.current)
                saveTimerRef.current = undefined
              }
              void flushSave()
            }}
          />
        </div>
      </div>
    </div>
  )
}
