import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { EditorView } from '@codemirror/view'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FrameGenJobStatus, NodeDocumentKind, NodeRecord } from '../../api/types'
import { useClarifyStore } from '../../stores/clarify-store'
import { useNodeDocumentStore } from '../../stores/node-document-store'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useProjectStore } from '../../stores/project-store'
import { api, ApiError } from '../../api/client'
import styles from './NodeDetailCard.module.css'

type EditorEntry = {
  content: string
  savedContent: string
  updatedAt: string | null
  isLoading: boolean
  isSaving: boolean
  error: string | null
  hasLoaded: boolean
}

const EMPTY_ENTRY: EditorEntry = {
  content: '',
  savedContent: '',
  updatedAt: null,
  isLoading: false,
  isSaving: false,
  error: null,
  hasLoaded: false,
}

type Props = {
  projectId: string
  node: NodeRecord
  kind: NodeDocumentKind
  onConfirm?: 'workflow'
  readOnly?: boolean
}

function documentStatusText(entry: EditorEntry, isGenerating: boolean): string {
  if (isGenerating) {
    return 'Generating...'
  }
  if (entry.isLoading && !entry.hasLoaded) {
    return 'Loading...'
  }
  if (entry.error) {
    return entry.error
  }
  if (entry.isSaving || entry.content !== entry.savedContent) {
    return 'Saving...'
  }
  return 'Saved'
}

export function NodeDocumentEditor({ projectId, node, kind, onConfirm, readOnly }: Props) {
  const entryKey = `${projectId}::${node.node_id}::${kind}`
  const entry = useNodeDocumentStore((state) => state.entries[entryKey] ?? EMPTY_ENTRY)
  const loadDocument = useNodeDocumentStore((state) => state.loadDocument)
  const updateDraft = useNodeDocumentStore((state) => state.updateDraft)
  const flushDocument = useNodeDocumentStore((state) => state.flushDocument)
  const invalidateDocument = useNodeDocumentStore((state) => state.invalidateEntry)
  const confirmFrame = useDetailStateStore((s) => s.confirmFrame)
  const confirmSpec = useDetailStateStore((s) => s.confirmSpec)
  const invalidateClarify = useClarifyStore((s) => s.invalidateEntry)
  const [isConfirming, setIsConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [genStatus, setGenStatus] = useState<FrameGenJobStatus>('idle')
  const [genError, setGenError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof globalThis.setInterval> | undefined>(undefined)

  const isGenerating = genStatus === 'active'

  // ── Document load / flush ────────────────────────────────────

  useEffect(() => {
    void loadDocument(projectId, node.node_id, kind).catch(() => undefined)
  }, [kind, loadDocument, node.node_id, projectId])

  useEffect(() => {
    return () => {
      void flushDocument(projectId, node.node_id, kind).catch(() => undefined)
    }
  }, [flushDocument, kind, node.node_id, projectId])

  // ── Generation: polling, recovery, trigger ───────────────────

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current !== undefined) {
        globalThis.clearInterval(pollRef.current)
      }
    }
  }, [])

  const pollGenStatus = kind === 'spec'
    ? api.getSpecGenStatus.bind(api)
    : api.getFrameGenStatus.bind(api)

  const startPolling = useCallback(() => {
    if (pollRef.current !== undefined) return
    pollRef.current = globalThis.setInterval(() => {
      void pollGenStatus(projectId, node.node_id).then((status) => {
        if (status.status !== 'active') {
          if (pollRef.current !== undefined) {
            globalThis.clearInterval(pollRef.current)
            pollRef.current = undefined
          }
          setGenStatus(status.status)
          if (status.status === 'failed') {
            setGenError(status.error ?? 'Generation failed')
          } else {
            // Reload document content after successful generation
            invalidateDocument(projectId, node.node_id, kind)
            void loadDocument(projectId, node.node_id, kind).catch(() => undefined)
          }
        }
      }).catch(() => {
        // Keep polling on transient errors
      })
    }, 2000)
  }, [projectId, node.node_id, kind, pollGenStatus, invalidateDocument, loadDocument])

  // Recover generation status on mount — attach to active jobs from prior navigation
  useEffect(() => {
    if (kind !== 'frame' && kind !== 'spec') return
    let cancelled = false
    void pollGenStatus(projectId, node.node_id).then((status) => {
      if (cancelled) return
      if (status.status === 'active') {
        setGenStatus('active')
        startPolling()
      } else if (status.status === 'failed') {
        setGenStatus('failed')
        setGenError(status.error ?? 'Generation failed')
      }
    }).catch(() => {
      // Ignore — status check is best-effort
    })
    return () => { cancelled = true }
  }, [kind, projectId, node.node_id, pollGenStatus, startPolling])

  const handleGenerate = useCallback(async () => {
    setGenError(null)
    try {
      await flushDocument(projectId, node.node_id, kind)
    } catch {
      setGenError('Could not save pending changes. Resolve the save error before generating.')
      return
    }
    setGenStatus('active')
    try {
      if (kind === 'spec') {
        await api.generateSpec(projectId, node.node_id)
      } else {
        await api.generateFrame(projectId, node.node_id)
      }
      startPolling()
    } catch (error) {
      const alreadyActiveCode = kind === 'spec'
        ? 'spec_generation_not_allowed'
        : 'frame_generation_not_allowed'
      if (error instanceof ApiError && error.code === alreadyActiveCode) {
        startPolling()
        return
      }
      setGenStatus('failed')
      setGenError(error instanceof Error ? error.message : 'Generate failed')
    }
  }, [projectId, node.node_id, kind, flushDocument, startPolling])

  // ── Confirm ──────────────────────────────────────────────────

  const handleConfirm = useCallback(async () => {
    if (onConfirm !== 'workflow') {
      void flushDocument(projectId, node.node_id, kind).catch(() => undefined)
      return
    }
    setIsConfirming(true)
    setConfirmError(null)
    try {
      await flushDocument(projectId, node.node_id, kind)
      if (kind === 'frame') {
        await confirmFrame(projectId, node.node_id)
        // Frame confirm re-seeds clarify on the backend — invalidate cached entry
        invalidateClarify(projectId, node.node_id)
        // Title may have changed — refresh snapshot so tree UI updates
        const snapshot = await api.getSnapshot(projectId)
        useProjectStore.setState((prev) => ({
          snapshot,
          selectedNodeId: prev.selectedNodeId,
        }))
        // If zero questions → spec generation triggered, invalidate spec doc
        const newDetailState = useDetailStateStore.getState().entries[detailStateKey]
        if (newDetailState?.active_step === 'spec') {
          invalidateDocument(projectId, node.node_id, 'spec')
        }
      } else if (kind === 'spec') {
        await confirmSpec(projectId, node.node_id)
      }
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Confirm failed')
    } finally {
      setIsConfirming(false)
    }
  }, [onConfirm, kind, flushDocument, projectId, node.node_id, confirmFrame, confirmSpec, invalidateClarify])

  // ── Derived state ────────────────────────────────────────────

  const detailStateKey = `${projectId}::${node.node_id}`
  const detailState = useDetailStateStore((s) => s.entries[detailStateKey])

  const isLoadError = Boolean(entry.error) && !entry.hasLoaded
  const isReadOnly = readOnly || isGenerating || (!entry.hasLoaded && (entry.isLoading || Boolean(entry.error)))
  const hasContent = entry.content.trim().length > 0
  const canConfirm = entry.hasLoaded && !isLoadError && !entry.isLoading && hasContent && !isConfirming && !isGenerating

  const confirmLabel = kind === 'frame' && detailState?.frame_needs_reconfirm
    ? 'Confirm Updated Frame'
    : 'Confirm'

  return (
    <div className={styles.documentPanel}>
      <div className={styles.documentMetaColumn}>
        <div className={styles.documentStatusRow}>
          <span className={styles.documentFileLabel}>{kind === 'frame' ? 'frame.md' : 'spec.md'}</span>
          <span
            className={`${styles.documentStatusValue} ${entry.error ? styles.documentStatusError : ''}`}
            data-testid={`document-status-${kind}`}
            role="status"
            aria-live="polite"
          >
            {documentStatusText(entry, isGenerating)}
          </span>
        </div>

        {isLoadError ? (
          <div className={styles.documentErrorPanel}>
            <p className={styles.body}>{entry.error}</p>
            <button
              type="button"
              className={styles.retryButton}
              onClick={() => {
                void loadDocument(projectId, node.node_id, kind).catch(() => undefined)
              }}
            >
              Retry
            </button>
          </div>
        ) : null}

        {confirmError ? (
          <div className={styles.documentErrorPanel} data-testid={`confirm-error-${kind}`}>
            <p className={styles.body}>{confirmError}</p>
          </div>
        ) : null}

        {genError ? (
          <div className={styles.documentErrorPanel} data-testid={`generate-error-${kind}`}>
            <p className={styles.body}>{genError}</p>
          </div>
        ) : null}
      </div>

      <div
        className={styles.editorSurface}
        aria-busy={Boolean(entry.isLoading && !entry.hasLoaded)}
      >
        <CodeMirror
          className={styles.codemirrorHost}
          value={entry.content}
          height="100%"
          extensions={[markdown(), EditorView.lineWrapping]}
          basicSetup={{
            foldGutter: false,
            lineNumbers: true,
          }}
          editable={!isReadOnly}
          onChange={(value) => {
            updateDraft(projectId, node.node_id, kind, value)
          }}
          onBlur={() => {
            void flushDocument(projectId, node.node_id, kind).catch(() => undefined)
          }}
        />
      </div>

      {!readOnly ? (
        <div className={styles.tabConfirmRow}>
          {(kind === 'frame' || kind === 'spec') ? (
            <button
              type="button"
              className={styles.generateButton}
              disabled={isGenerating || isConfirming}
              data-testid={`generate-${kind}-button`}
              onClick={handleGenerate}
            >
              {isGenerating
                ? 'Generating...'
                : kind === 'spec'
                  ? 'Regenerate Spec'
                  : 'Generate from Chat'}
            </button>
          ) : null}
          <button
            type="button"
            className={styles.confirmButton}
            disabled={!canConfirm || entry.isSaving}
            data-testid={`confirm-document-${kind}`}
            onClick={handleConfirm}
          >
            {isConfirming ? 'Confirming...' : confirmLabel}
          </button>
        </div>
      ) : null}
    </div>
  )
}
