import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { useCallback, useEffect, useState } from 'react'
import type { NodeDocumentKind, NodeRecord } from '../../api/types'
import { useNodeDocumentStore } from '../../stores/node-document-store'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useProjectStore } from '../../stores/project-store'
import { api } from '../../api/client'
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
}

function documentStatusText(entry: EditorEntry): string {
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

export function NodeDocumentEditor({ projectId, node, kind, onConfirm }: Props) {
  const entryKey = `${projectId}::${node.node_id}::${kind}`
  const entry = useNodeDocumentStore((state) => state.entries[entryKey] ?? EMPTY_ENTRY)
  const loadDocument = useNodeDocumentStore((state) => state.loadDocument)
  const updateDraft = useNodeDocumentStore((state) => state.updateDraft)
  const flushDocument = useNodeDocumentStore((state) => state.flushDocument)
  const confirmFrame = useDetailStateStore((s) => s.confirmFrame)
  const confirmSpec = useDetailStateStore((s) => s.confirmSpec)
  const [isConfirming, setIsConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState<string | null>(null)

  useEffect(() => {
    void loadDocument(projectId, node.node_id, kind).catch(() => undefined)
  }, [kind, loadDocument, node.node_id, projectId])

  useEffect(() => {
    return () => {
      void flushDocument(projectId, node.node_id, kind).catch(() => undefined)
    }
  }, [flushDocument, kind, node.node_id, projectId])

  const isLoadError = Boolean(entry.error) && !entry.hasLoaded
  const isReadOnly = !entry.hasLoaded && (entry.isLoading || Boolean(entry.error))

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
        // Title may have changed — refresh snapshot so tree UI updates
        const snapshot = await api.getSnapshot(projectId)
        useProjectStore.setState((prev) => ({
          snapshot,
          selectedNodeId: prev.selectedNodeId,
        }))
      } else if (kind === 'spec') {
        await confirmSpec(projectId, node.node_id)
      }
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Confirm failed')
    } finally {
      setIsConfirming(false)
    }
  }, [onConfirm, kind, flushDocument, projectId, node.node_id, confirmFrame, confirmSpec])

  const hasContent = entry.content.trim().length > 0
  const canConfirm = entry.hasLoaded && !isLoadError && !entry.isLoading && hasContent && !isConfirming

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
            {documentStatusText(entry)}
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
      </div>

      <div
        className={styles.editorSurface}
        aria-busy={Boolean(entry.isLoading && !entry.hasLoaded)}
      >
        <CodeMirror
          value={entry.content}
          height="100%"
          extensions={[markdown()]}
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

      <div className={styles.tabConfirmRow}>
        <button
          type="button"
          className={styles.confirmButton}
          disabled={!canConfirm || entry.isSaving}
          data-testid={`confirm-document-${kind}`}
          onClick={handleConfirm}
        >
          {isConfirming ? 'Confirming...' : 'Confirm'}
        </button>
      </div>
    </div>
  )
}
