import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { EditorView } from '@codemirror/view'
import { useCallback, useEffect, useRef, useState } from 'react'
import type { FrameGenJobStatus, NodeDocumentKind, NodeRecord } from '../../api/types'
import { api, ApiError } from '../../api/client'
import { AgentSpinner, SPINNER_WORDS_GENERATING } from '../../components/AgentSpinner'
import { useClarifyStore } from '../../stores/clarify-store'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useNodeDocumentStore } from '../../stores/node-document-store'
import { useProjectStore } from '../../stores/project-store'
import type { WorkflowTab } from './WorkflowStepper'
import { vscodeMarkdownSyntaxHighlighting } from './codemirror/vscodeMarkdownHighlight'
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
  workflowTab?: WorkflowTab
  onWorkflowTabChange?: (tab: WorkflowTab) => void
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

export function NodeDocumentEditor({
  projectId,
  node,
  kind,
  workflowTab,
  onWorkflowTabChange,
  onConfirm,
  readOnly,
}: Props) {
  const entryKey = `${projectId}::${node.node_id}::${kind}`
  const detailStateKey = `${projectId}::${node.node_id}`
  const entry = useNodeDocumentStore((state) => state.entries[entryKey] ?? EMPTY_ENTRY)
  const loadDocument = useNodeDocumentStore((state) => state.loadDocument)
  const updateDraft = useNodeDocumentStore((state) => state.updateDraft)
  const flushDocument = useNodeDocumentStore((state) => state.flushDocument)
  const invalidateDocument = useNodeDocumentStore((state) => state.invalidateEntry)
  const confirmFrame = useDetailStateStore((state) => state.confirmFrame)
  const confirmSpec = useDetailStateStore((state) => state.confirmSpec)
  const finishTask = useDetailStateStore((state) => state.finishTask)
  const loadDetailState = useDetailStateStore((state) => state.loadDetailState)
  const detailState = useDetailStateStore((state) => state.entries[detailStateKey])
  const isFinishingTask = useDetailStateStore((state) => state.finishingTask[detailStateKey] ?? false)
  const invalidateClarify = useClarifyStore((state) => state.invalidateEntry)
  const [isConfirming, setIsConfirming] = useState(false)
  const [pendingAction, setPendingAction] = useState<'confirm' | 'split' | 'create_spec' | 'finish' | null>(null)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [genStatus, setGenStatus] = useState<FrameGenJobStatus>('idle')
  const [genError, setGenError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof globalThis.setInterval> | undefined>(undefined)

  const isGenerating = genStatus === 'active'
  const isInitialFrameStep = kind === 'frame' && workflowTab !== 'frame_updated'
  const isUpdatedFrameStep = kind === 'frame' && workflowTab === 'frame_updated'
  const isSpecStep = kind === 'spec'

  useEffect(() => {
    void loadDocument(projectId, node.node_id, kind).catch(() => undefined)
  }, [kind, loadDocument, node.node_id, projectId])

  useEffect(() => {
    return () => {
      void flushDocument(projectId, node.node_id, kind).catch(() => undefined)
    }
  }, [flushDocument, kind, node.node_id, projectId])

  useEffect(() => {
    return () => {
      if (pollRef.current !== undefined) {
        globalThis.clearInterval(pollRef.current)
      }
    }
  }, [])

  const refreshSnapshot = useCallback(async () => {
    const snapshot = await api.getSnapshot(projectId)
    useProjectStore.setState((prev) => ({
      snapshot,
      selectedNodeId: prev.selectedNodeId,
    }))
  }, [projectId])

  const pollGenStatus = kind === 'spec'
    ? api.getSpecGenStatus.bind(api)
    : api.getFrameGenStatus.bind(api)

  const startPolling = useCallback(() => {
    if (pollRef.current !== undefined) {
      return
    }
    pollRef.current = globalThis.setInterval(() => {
      void pollGenStatus(projectId, node.node_id)
        .then((status) => {
          if (status.status === 'active') {
            return
          }
          if (pollRef.current !== undefined) {
            globalThis.clearInterval(pollRef.current)
            pollRef.current = undefined
          }
          setGenStatus(status.status)
          if (status.status === 'failed') {
            setGenError(status.error ?? 'Generation failed')
            return
          }
          invalidateDocument(projectId, node.node_id, kind)
          void loadDocument(projectId, node.node_id, kind).catch(() => undefined)
          void loadDetailState(projectId, node.node_id).catch(() => undefined)
        })
        .catch(() => {
          // Keep polling on transient errors.
        })
    }, 2000)
  }, [invalidateDocument, kind, loadDetailState, loadDocument, node.node_id, pollGenStatus, projectId])

  useEffect(() => {
    if (kind !== 'frame' && kind !== 'spec') {
      return
    }
    let cancelled = false
    void pollGenStatus(projectId, node.node_id)
      .then((status) => {
        if (cancelled) {
          return
        }
        if (status.status === 'active') {
          setGenStatus('active')
          startPolling()
        } else if (status.status === 'failed') {
          setGenStatus('failed')
          setGenError(status.error ?? 'Generation failed')
        }
      })
      .catch(() => {
        // Status recovery is best effort.
      })
    return () => {
      cancelled = true
    }
  }, [kind, node.node_id, pollGenStatus, projectId, startPolling])

  const handleGenerateFrame = useCallback(async () => {
    setGenError(null)
    try {
      await flushDocument(projectId, node.node_id, kind)
    } catch {
      setGenError('Could not save pending changes. Resolve the save error before generating.')
      return
    }

    setGenStatus('active')
    try {
      await api.generateFrame(projectId, node.node_id)
      startPolling()
    } catch (error) {
      if (error instanceof ApiError && error.code === 'frame_generation_not_allowed') {
        startPolling()
        return
      }
      setGenStatus('failed')
      setGenError(error instanceof Error ? error.message : 'Generate failed')
    }
  }, [flushDocument, kind, node.node_id, projectId, startPolling])

  const handleConfirmFrame = useCallback(async () => {
    await flushDocument(projectId, node.node_id, 'frame')
    const nextState = await confirmFrame(projectId, node.node_id)
    invalidateClarify(projectId, node.node_id)
    invalidateDocument(projectId, node.node_id, 'spec')
    await refreshSnapshot()
    return nextState
  }, [
    confirmFrame,
    flushDocument,
    invalidateClarify,
    invalidateDocument,
    node.node_id,
    projectId,
    refreshSnapshot,
  ])

  const handleConfirmAndCreateSpec = useCallback(async () => {
    setIsConfirming(true)
    setPendingAction('create_spec')
    setConfirmError(null)

    try {
      await flushDocument(projectId, node.node_id, 'frame')

      if (detailState?.frame_needs_reconfirm || detailState?.frame_confirmed !== true) {
        await handleConfirmFrame()
      }

      invalidateDocument(projectId, node.node_id, 'spec')

      try {
        await api.generateSpec(projectId, node.node_id)
      } catch (error) {
        if (!(error instanceof ApiError && error.code === 'spec_generation_not_allowed')) {
          throw error
        }
      }

      await loadDetailState(projectId, node.node_id)
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Create spec failed')
    } finally {
      setPendingAction(null)
      setIsConfirming(false)
    }
  }, [
    detailState?.frame_confirmed,
    detailState?.frame_needs_reconfirm,
    flushDocument,
    handleConfirmFrame,
    invalidateDocument,
    loadDetailState,
    node.node_id,
    projectId,
  ])

  const handleConfirmAndSplit = useCallback(async () => {
    setIsConfirming(true)
    setPendingAction('split')
    setConfirmError(null)

    try {
      await handleConfirmFrame()
      onWorkflowTabChange?.('split')
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Split prep failed')
    } finally {
      setPendingAction(null)
      setIsConfirming(false)
    }
  }, [handleConfirmFrame, onWorkflowTabChange])

  const handleConfirmAndFinish = useCallback(async () => {
    setIsConfirming(true)
    setPendingAction('finish')
    setConfirmError(null)

    try {
      await flushDocument(projectId, node.node_id, 'spec')
      await confirmSpec(projectId, node.node_id)
      await refreshSnapshot()
      await finishTask(projectId, node.node_id)

      const finishError = useDetailStateStore.getState().errors[detailStateKey]
      if (finishError) {
        setConfirmError(finishError)
      }
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Finish task failed')
    } finally {
      setPendingAction(null)
      setIsConfirming(false)
    }
  }, [confirmSpec, detailStateKey, finishTask, flushDocument, node.node_id, projectId, refreshSnapshot])

  const handleConfirm = useCallback(async () => {
    if (onConfirm !== 'workflow') {
      void flushDocument(projectId, node.node_id, kind).catch(() => undefined)
      return
    }

    setIsConfirming(true)
    setPendingAction('confirm')
    setConfirmError(null)

    try {
      if (kind === 'frame') {
        await handleConfirmFrame()
      } else if (kind === 'spec') {
        await handleConfirmAndFinish()
        return
      }
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Confirm failed')
    } finally {
      setPendingAction(null)
      setIsConfirming(false)
    }
  }, [
    flushDocument,
    handleConfirmAndFinish,
    handleConfirmFrame,
    kind,
    node.node_id,
    onConfirm,
    projectId,
  ])

  const isLoadError = Boolean(entry.error) && !entry.hasLoaded
  const isReadOnly =
    Boolean(readOnly) ||
    isGenerating ||
    (!entry.hasLoaded && (entry.isLoading || Boolean(entry.error)))
  const hasContent = entry.content.trim().length > 0
  const canConfirm =
    entry.hasLoaded &&
    !isLoadError &&
    !entry.isLoading &&
    hasContent &&
    !isConfirming &&
    !isGenerating &&
    !entry.isSaving
  const canFinishTask = canConfirm && !isFinishingTask && detailState?.git_ready !== false

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
            {isGenerating ? (
              <AgentSpinner words={SPINNER_WORDS_GENERATING} />
            ) : (
              documentStatusText(entry, false)
            )}
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
          theme="none"
          extensions={[markdown(), vscodeMarkdownSyntaxHighlighting, EditorView.lineWrapping]}
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
          {isInitialFrameStep ? (
            <>
              <button
                type="button"
                className={styles.generateButton}
                disabled={isGenerating || isConfirming}
                data-testid="generate-frame-button"
                onClick={handleGenerateFrame}
              >
                {isGenerating ? <AgentSpinner words={SPINNER_WORDS_GENERATING} /> : 'Generate from Chat'}
              </button>
              <button
                type="button"
                className={styles.confirmButton}
                disabled={!canConfirm}
                data-testid="confirm-document-frame"
                onClick={handleConfirm}
              >
                {isConfirming ? 'Confirming...' : 'Confirm'}
              </button>
            </>
          ) : null}

          {isUpdatedFrameStep ? (
            <>
              <button
                type="button"
                className={styles.generateButton}
                disabled={!canConfirm}
                data-testid="confirm-and-split-button"
                onClick={handleConfirmAndSplit}
              >
                {pendingAction === 'split' ? 'Preparing Split...' : 'Confirm and Split'}
              </button>
              <button
                type="button"
                className={styles.confirmButton}
                disabled={!canConfirm}
                data-testid="confirm-and-create-spec-button"
                onClick={handleConfirmAndCreateSpec}
              >
                {pendingAction === 'create_spec' ? 'Creating Spec...' : 'Confirm and Create Spec'}
              </button>
            </>
          ) : null}

          {isSpecStep ? (
            <button
              type="button"
              className={styles.confirmButton}
              disabled={!canFinishTask}
              data-testid="confirm-and-finish-task-button"
              onClick={handleConfirmAndFinish}
            >
              {pendingAction === 'finish' || isFinishingTask ? 'Finishing...' : 'Confirm and Finish Task'}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
