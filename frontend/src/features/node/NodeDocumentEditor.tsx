import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { useEffect } from 'react'
import type { NodeDocumentKind, NodeRecord } from '../../api/types'
import { useNodeDocumentStore } from '../../stores/node-document-store'
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

export function NodeDocumentEditor({ projectId, node, kind }: Props) {
  const entryKey = `${projectId}::${node.node_id}::${kind}`
  const entry = useNodeDocumentStore((state) => state.entries[entryKey] ?? EMPTY_ENTRY)
  const loadDocument = useNodeDocumentStore((state) => state.loadDocument)
  const updateDraft = useNodeDocumentStore((state) => state.updateDraft)
  const flushDocument = useNodeDocumentStore((state) => state.flushDocument)

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

  return (
    <div className={styles.documentPanel}>
      <div className={styles.contentPanel}>
        <p className={styles.eyebrow}>
          {node.hierarchical_number ? `${node.hierarchical_number} - Node` : 'Node'}
        </p>
        <h3 className={styles.title}>{node.title}</h3>
        <p className={styles.body}>{node.description.trim() || 'No description yet.'}</p>
        <p className={styles.body}>
          Status: <strong>{node.status}</strong> . Children: {node.child_ids.length}
        </p>
      </div>

      <div className={styles.documentStatusRow}>
        <span className={styles.documentFileLabel}>{kind === 'frame' ? 'frame.md' : 'spec.md'}</span>
        <span
          className={`${styles.documentStatusValue} ${entry.error ? styles.documentStatusError : ''}`}
          data-testid={`document-status-${kind}`}
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

      <div className={styles.editorSurface}>
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
    </div>
  )
}
