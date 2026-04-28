import CodeMirror from '@uiw/react-codemirror'
import { markdown } from '@codemirror/lang-markdown'
import { EditorView } from '@codemirror/view'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import type { FrameGenJobStatus, NodeDocumentKind, NodeRecord } from '../../api/types'
import { api, ApiError } from '../../api/client'
import { AgentSpinner, SPINNER_WORDS_GENERATING } from '../../components/AgentSpinner'
import { useClarifyStore } from '../../stores/clarify-store'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useNodeDocumentStore } from '../../stores/node-document-store'
import { useProjectStore } from '../../stores/project-store'
import { useAskShellActionStore } from '../../stores/ask-shell-action-store'
import { buildChatV2Url } from '../conversation/surfaceRouting'
import {
  captureWorkflowStreamCursor,
  primeAndSelectWorkflowTurn,
} from '../session_v2/facade/workflowLiveTurnBridge'
import { useWorkflowStateV2 } from '../workflow_v2/hooks/useWorkflowStateV2'
import { DocumentRichViewContent } from '../markdown/DocumentRichView'
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

export type FramePostUpdateBranch = 'none' | 'spec' | 'split'

type Props = {
  projectId: string
  node: NodeRecord
  kind: NodeDocumentKind
  workflowTab?: WorkflowTab
  onWorkflowTabChange?: (tab: WorkflowTab) => void
  onConfirm?: 'workflow'
  readOnly?: boolean
  /** Tracks spec vs split commitment after Frame updated (for mutual exclusivity). */
  framePostUpdateBranch?: FramePostUpdateBranch
  splitConfirmed?: boolean
  onFramePostUpdateCommit?: (branch: 'spec' | 'split') => void
  /** Breadcrumb: replaces frame.md/spec.md label in the toolbar row */
  documentToolbarTabs?: ReactNode
}

export function NodeDocumentEditor({
  projectId,
  node,
  kind,
  workflowTab,
  onWorkflowTabChange,
  onConfirm,
  readOnly,
  framePostUpdateBranch = 'none',
  splitConfirmed = false,
  onFramePostUpdateCommit,
  documentToolbarTabs,
}: Props) {
  const navigate = useNavigate()
  const entryKey = `${projectId}::${node.node_id}::${kind}`
  const detailStateKey = `${projectId}::${node.node_id}`
  const entry = useNodeDocumentStore((state) => state.entries[entryKey] ?? EMPTY_ENTRY)
  const loadDocument = useNodeDocumentStore((state) => state.loadDocument)
  const updateDraft = useNodeDocumentStore((state) => state.updateDraft)
  const flushDocument = useNodeDocumentStore((state) => state.flushDocument)
  const invalidateDocument = useNodeDocumentStore((state) => state.invalidateEntry)
  const confirmFrame = useDetailStateStore((state) => state.confirmFrame)
  const confirmSpec = useDetailStateStore((state) => state.confirmSpec)
  const loadDetailState = useDetailStateStore((state) => state.loadDetailState)
  const detailState = useDetailStateStore((state) => state.entries[detailStateKey])
  const markActionRunning = useAskShellActionStore((state) => state.markRunning)
  const markActionSucceeded = useAskShellActionStore((state) => state.markSucceeded)
  const markActionFailed = useAskShellActionStore((state) => state.markFailed)
  const invalidateClarify = useClarifyStore((state) => state.invalidateEntry)
  const {
    workflowState,
    startExecution,
    activeMutation: activeWorkflowMutation,
  } = useWorkflowStateV2(projectId, node.node_id)
  const projectRootPath = useProjectStore((state) =>
    state.snapshot?.project.id === projectId
      ? state.snapshot.project.project_path
      : undefined,
  )
  const [isConfirming, setIsConfirming] = useState(false)
  const [pendingAction, setPendingAction] = useState<'confirm' | 'split' | 'create_spec' | 'finish' | null>(null)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [genStatus, setGenStatus] = useState<FrameGenJobStatus>('idle')
  const [genError, setGenError] = useState<string | null>(null)
  const [hasGeneratedArtifact, setHasGeneratedArtifact] = useState(false)
  const [viewMode, setViewMode] = useState<'edit' | 'rich'>('edit')
  const pollRef = useRef<ReturnType<typeof globalThis.setInterval> | undefined>(undefined)
  const editorSurfaceRef = useRef<HTMLDivElement>(null)
  const [isFinishLocked, setIsFinishLocked] = useState(false)
  const isFinishingTask = activeWorkflowMutation === 'start_execution'
  const isFinishActionPending = pendingAction === 'finish' || isFinishingTask

  const handleCopyDocument = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(entry.content)
    } catch {
      /* clipboard may be unavailable */
    }
  }, [entry.content])

  const handleEditorFullscreen = useCallback(() => {
    const el = editorSurfaceRef.current
    if (!el) return
    if (document.fullscreenElement === el) {
      void document.exitFullscreen()
    } else {
      void el.requestFullscreen().catch(() => undefined)
    }
  }, [])

  const isGenerating = genStatus === 'active'
  const isRichView = viewMode === 'rich'
  const isInitialFrameStep = kind === 'frame' && workflowTab !== 'frame_updated'
  const isUpdatedFrameStep = kind === 'frame' && workflowTab === 'frame_updated'
  const isSpecStep = kind === 'spec'

  const confirmAndSplitDisabled = framePostUpdateBranch === 'spec' || splitConfirmed
  const confirmAndCreateSpecDisabled = framePostUpdateBranch === 'split' || splitConfirmed

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
        pollRef.current = undefined
      }
    }
  }, [kind, node.node_id, projectId])

  useEffect(() => {
    setViewMode('edit')
  }, [kind, node.node_id, projectId])

  useEffect(() => {
    setIsFinishLocked(false)
  }, [projectId, node.node_id])

  useEffect(() => {
    setHasGeneratedArtifact(false)
  }, [kind, node.node_id, projectId])

  const refreshSnapshot = useCallback(async () => {
    const snapshot = await api.getSnapshot(projectId)
    useProjectStore.setState((prev) => ({
      snapshot,
      selectedNodeId: prev.selectedNodeId,
    }))
  }, [projectId])

  const pollGenStatus = useCallback(
    (activeProjectId: string, activeNodeId: string) => (
      kind === 'spec'
        ? api.getSpecGenStatus(activeProjectId, activeNodeId)
        : api.getFrameGenStatus(activeProjectId, activeNodeId)
    ),
    [kind],
  )

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
            markActionFailed(
              projectId,
              node.node_id,
              kind === 'spec' ? 'spec' : 'frame',
              'generate',
              status.error ?? 'Generation failed',
            )
            return
          }
          markActionSucceeded(
            projectId,
            node.node_id,
            kind === 'spec' ? 'spec' : 'frame',
            'generate',
          )
          setHasGeneratedArtifact(true)
          invalidateDocument(projectId, node.node_id, kind)
          void loadDocument(projectId, node.node_id, kind).catch(() => undefined)
          void loadDetailState(projectId, node.node_id).catch(() => undefined)
        })
        .catch(() => {
          // Keep polling on transient errors.
        })
    }, 2000)
  }, [
    invalidateDocument,
    kind,
    loadDetailState,
    loadDocument,
    markActionFailed,
    markActionSucceeded,
    node.node_id,
    pollGenStatus,
    projectId,
  ])

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
          markActionRunning(
            projectId,
            node.node_id,
            kind === 'spec' ? 'spec' : 'frame',
            'generate',
          )
          startPolling()
        } else if (status.status === 'failed') {
          setGenStatus('failed')
          setGenError(status.error ?? 'Generation failed')
          markActionFailed(
            projectId,
            node.node_id,
            kind === 'spec' ? 'spec' : 'frame',
            'generate',
            status.error ?? 'Generation failed',
          )
        } else if (status.completed_at) {
          setHasGeneratedArtifact(true)
        }
      })
      .catch(() => {
        // Status recovery is best effort.
      })
    return () => {
      cancelled = true
    }
  }, [
    kind,
    markActionFailed,
    markActionRunning,
    node.node_id,
    pollGenStatus,
    projectId,
    startPolling,
  ])

  const triggerClarifyGeneration = useCallback(
    async (activeProjectId: string, activeNodeId: string) => {
      markActionRunning(activeProjectId, activeNodeId, 'clarify', 'generate')
      try {
        await api.generateClarify(activeProjectId, activeNodeId)
      } catch (error) {
        if (error instanceof ApiError && error.code === 'clarify_generation_not_allowed') {
          return
        }
        markActionFailed(
          activeProjectId,
          activeNodeId,
          'clarify',
          'generate',
          error instanceof Error ? error.message : 'Generate clarify failed',
        )
      }
    },
    [markActionFailed, markActionRunning],
  )

  const handleGenerateDocument = useCallback(async () => {
    if (kind !== 'frame' && kind !== 'spec') {
      return
    }
    setGenError(null)
    try {
      await flushDocument(projectId, node.node_id, kind)
    } catch {
      setGenError('Could not save pending changes. Resolve the save error before generating.')
      return
    }

    setGenStatus('active')
    const artifact = kind === 'spec' ? 'spec' : 'frame'
    markActionRunning(projectId, node.node_id, artifact, 'generate')
    try {
      if (kind === 'spec') {
        await api.generateSpec(projectId, node.node_id)
      } else {
        await api.generateFrame(projectId, node.node_id)
      }
      startPolling()
    } catch (error) {
      const generationNotAllowedCode =
        kind === 'spec' ? 'spec_generation_not_allowed' : 'frame_generation_not_allowed'
      if (error instanceof ApiError && error.code === generationNotAllowedCode) {
        startPolling()
        return
      }
      setGenStatus('failed')
      const message = error instanceof Error ? error.message : 'Generate failed'
      setGenError(message)
      markActionFailed(projectId, node.node_id, artifact, 'generate', message)
    }
  }, [
    flushDocument,
    kind,
    markActionFailed,
    markActionRunning,
    node.node_id,
    projectId,
    startPolling,
  ])

  const handleConfirmFrame = useCallback(async (options?: { autoGenerateClarify?: boolean }) => {
    const shouldAutoGenerateClarify = options?.autoGenerateClarify === true
    markActionRunning(projectId, node.node_id, 'frame', 'confirm')
    try {
      await flushDocument(projectId, node.node_id, 'frame')
      const nextState = await confirmFrame(projectId, node.node_id)
      invalidateClarify(projectId, node.node_id)
      invalidateDocument(projectId, node.node_id, 'spec')
      if (shouldAutoGenerateClarify && nextState?.clarify_confirmed !== true) {
        await triggerClarifyGeneration(projectId, node.node_id)
      }
      await refreshSnapshot()
      markActionSucceeded(projectId, node.node_id, 'frame', 'confirm')
      return nextState
    } catch (error) {
      markActionFailed(
        projectId,
        node.node_id,
        'frame',
        'confirm',
        error instanceof Error ? error.message : 'Confirm failed',
      )
      throw error
    }
  }, [
    confirmFrame,
    flushDocument,
    invalidateClarify,
    invalidateDocument,
    markActionFailed,
    markActionRunning,
    markActionSucceeded,
    node.node_id,
    projectId,
    refreshSnapshot,
    triggerClarifyGeneration,
  ])

  const handleConfirmAndCreateSpec = useCallback(async () => {
    setIsConfirming(true)
    setPendingAction('create_spec')
    setConfirmError(null)

    try {
      await flushDocument(projectId, node.node_id, 'frame')

      if (detailState?.frame_needs_reconfirm || detailState?.frame_confirmed !== true) {
        await handleConfirmFrame({ autoGenerateClarify: false })
      }

      invalidateDocument(projectId, node.node_id, 'spec')

      try {
        markActionRunning(projectId, node.node_id, 'spec', 'generate')
        await api.generateSpec(projectId, node.node_id)
      } catch (error) {
        if (!(error instanceof ApiError && error.code === 'spec_generation_not_allowed')) {
          markActionFailed(
            projectId,
            node.node_id,
            'spec',
            'generate',
            error instanceof Error ? error.message : 'Generate spec failed',
          )
          throw error
        }
      }

      onFramePostUpdateCommit?.('spec')
      await loadDetailState(projectId, node.node_id)
      onWorkflowTabChange?.('spec')
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
    markActionFailed,
    markActionRunning,
    node.node_id,
    onWorkflowTabChange,
    onFramePostUpdateCommit,
    projectId,
  ])

  const handleConfirmAndSplit = useCallback(async () => {
    setIsConfirming(true)
    setPendingAction('split')
    setConfirmError(null)

    try {
      await handleConfirmFrame()
      onFramePostUpdateCommit?.('split')
      onWorkflowTabChange?.('split')
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Split prep failed')
    } finally {
      setPendingAction(null)
      setIsConfirming(false)
    }
  }, [handleConfirmFrame, onFramePostUpdateCommit, onWorkflowTabChange])

  const handleConfirmAndFinish = useCallback(async () => {
    if (pendingAction === 'finish' || isFinishingTask || isFinishLocked) {
      return
    }
    setIsConfirming(true)
    setPendingAction('finish')
    setConfirmError(null)

    try {
      await flushDocument(projectId, node.node_id, 'spec')
      markActionRunning(projectId, node.node_id, 'spec', 'confirm')
      try {
        await confirmSpec(projectId, node.node_id)
        markActionSucceeded(projectId, node.node_id, 'spec', 'confirm')
      } catch (error) {
        markActionFailed(
          projectId,
          node.node_id,
          'spec',
          'confirm',
          error instanceof Error ? error.message : 'Confirm spec failed',
        )
        throw error
      }
      await refreshSnapshot()
      const preActionCursor = captureWorkflowStreamCursor(workflowState?.threads.execution ?? null)
      const result = await startExecution(projectId, node.node_id)
      const executionThreadId =
        result.threadId ?? result.workflowState?.threads.execution ?? workflowState?.threads.execution ?? null
      await primeAndSelectWorkflowTurn({
        actionKind: 'start_execution',
        targetLane: 'execution',
        threadId: executionThreadId,
        turnId: result.turnId ?? null,
        projectId,
        nodeId: node.node_id,
        preActionCursor,
      })
      navigate(buildChatV2Url(projectId, node.node_id, 'execution'))
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Finish task failed')
    } finally {
      setPendingAction(null)
      setIsConfirming(false)
    }
  }, [
    confirmSpec,
    flushDocument,
    isFinishingTask,
    isFinishLocked,
    markActionFailed,
    markActionRunning,
    markActionSucceeded,
    navigate,
    node.node_id,
    pendingAction,
    projectId,
    refreshSnapshot,
    startExecution,
    workflowState?.threads.execution,
  ])

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
        await handleConfirmFrame({ autoGenerateClarify: true })
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
  const isSaveError = Boolean(entry.error) && entry.hasLoaded
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
  const canFinishTaskAfterConfirm =
    node.node_kind !== 'review' &&
    node.child_ids.length === 0 &&
    (node.status === 'ready' || node.status === 'in_progress') &&
    detailState?.shaping_frozen !== true &&
    detailState?.git_ready !== false
  const isArtifactActionBusy = isGenerating || isConfirming || pendingAction !== null
  const canFinishTask =
    canConfirm &&
    !isFinishActionPending &&
    (
      detailState?.can_finish_task === true ||
      (detailState?.spec_confirmed !== true && canFinishTaskAfterConfirm)
    )
  const isFinishTaskDisabled = isFinishLocked || isArtifactActionBusy || !canFinishTask || isFinishActionPending
  const frameGenerateLabel = hasGeneratedArtifact ? 'Regenerate Frame' : 'Generate Frame'
  const specGenerateLabel = hasGeneratedArtifact ? 'Regenerate Spec' : 'Generate Spec'
  const finishTaskDisabledHint = (() => {
    if (!isSpecStep || !isFinishTaskDisabled) {
      return null
    }
    if (isFinishLocked) {
      return 'Finish Task was already confirmed for this run.'
    }
    if (isFinishActionPending) {
      return 'Processing finish task request...'
    }
    if (isArtifactActionBusy) {
      return 'Another action is in progress. Please wait.'
    }
    if (!hasContent) {
      return 'Add spec content before finishing the task.'
    }
    if (entry.isLoading) {
      return 'Spec is loading. Please wait.'
    }
    if (entry.isSaving) {
      return 'Spec is saving. Please wait.'
    }
    if (isGenerating) {
      return 'Spec generation is running. Please wait.'
    }
    if (detailState?.git_ready === false) {
      return 'Finish Task is disabled. Resolve Git blocker to continue.'
    }
    if (detailState?.shaping_frozen === true) {
      return 'Task is read-only while execution is active.'
    }
    return 'Finish Task is currently unavailable.'
  })()

  return (
    <div className={styles.documentPanel}>
      <div className={styles.documentMetaColumn}>
        <div
          className={
            documentToolbarTabs
              ? `${styles.documentStatusRow} ${styles.documentStatusRowEmbedTabs}`
              : styles.documentStatusRow
          }
        >
          {documentToolbarTabs ? (
            documentToolbarTabs
          ) : (
            <div className={styles.documentFileLabelCell}>
              <span className={styles.documentFileLabelIcon} aria-hidden="true">
                <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" width="13" height="13">
                  <path d="M4 2h6l3 3v9a1 1 0 01-1 1H4a1 1 0 01-1-1V3a1 1 0 011-1z" />
                  <path d="M10 2v4h3" />
                </svg>
              </span>
              <span className={styles.documentFileLabel}>{kind === 'frame' ? 'frame.md' : 'spec.md'}</span>
            </div>
          )}
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

        {isSaveError ? (
          <div className={styles.documentErrorPanel} data-testid={`save-error-${kind}`} role="alert">
            <p className={styles.body}>{entry.error}</p>
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
        ref={editorSurfaceRef}
        className={styles.editorSurface}
        aria-busy={Boolean(entry.isLoading && !entry.hasLoaded)}
      >
        <div className={styles.editorSurfaceHeader}>
          <div className={styles.editorSurfaceHeaderMain}>
            <span className={styles.editorSurfaceTitle}>Markdown editor</span>
            <div
              className={styles.editorModeToggle}
              role="group"
              aria-label={`${kind} document view mode`}
            >
              <button
                type="button"
                className={`${styles.editorModeToggleButton} ${!isRichView ? styles.editorModeToggleButtonActive : ''}`}
                data-testid={`document-view-edit-${kind}`}
                aria-pressed={!isRichView}
                onClick={() => {
                  setViewMode('edit')
                }}
              >
                Edit
              </button>
              <button
                type="button"
                className={`${styles.editorModeToggleButton} ${isRichView ? styles.editorModeToggleButtonActive : ''}`}
                data-testid={`document-view-rich-${kind}`}
                aria-pressed={isRichView}
                onClick={() => {
                  setViewMode('rich')
                }}
              >
                Rich View
              </button>
            </div>
          </div>
          <div className={styles.editorSurfaceHeaderActions}>
            <button
              type="button"
              className={styles.editorSurfaceHeaderIcon}
              onClick={() => {
                void handleCopyDocument()
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
          {isGenerating ? (
            <div className={styles.editorGeneratingBody} data-testid={`document-generating-${kind}`}>
              <AgentSpinner words={SPINNER_WORDS_GENERATING} />
            </div>
          ) : (
            <>
              {isRichView ? (
                <DocumentRichViewContent
                  content={entry.content}
                  projectRootPath={projectRootPath}
                  testId={`document-rich-view-${kind}`}
                />
              ) : (
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
              )}
            </>
          )}
        </div>
      </div>

      {!readOnly ? (
        <div className={styles.tabConfirmRow}>
          {isInitialFrameStep ? (
            <>
              <button
                type="button"
                className={styles.generateButton}
                disabled={isArtifactActionBusy}
                data-testid="generate-frame-button"
                onClick={handleGenerateDocument}
              >
                {frameGenerateLabel}
              </button>
              <button
                type="button"
                className={styles.confirmButton}
                disabled={!canConfirm || isArtifactActionBusy}
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
                disabled={!canConfirm || confirmAndSplitDisabled || isArtifactActionBusy}
                data-testid="confirm-and-split-button"
                onClick={handleConfirmAndSplit}
                title={
                  splitConfirmed
                    ? 'This node has already been split'
                    : confirmAndSplitDisabled
                      ? 'You already committed to Create Spec from Frame updated'
                      : undefined
                }
              >
                Confirm and Split
              </button>
              <button
                type="button"
                className={styles.confirmButton}
                disabled={!canConfirm || confirmAndCreateSpecDisabled || isArtifactActionBusy}
                data-testid="confirm-and-create-spec-button"
                onClick={handleConfirmAndCreateSpec}
                title={
                  splitConfirmed
                    ? 'This node has already been split'
                    : confirmAndCreateSpecDisabled
                      ? 'You already committed to Split from Frame updated'
                      : undefined
                }
              >
                Confirm and Create Spec
              </button>
            </>
          ) : null}

          {isSpecStep ? (
            <>
              <button
                type="button"
                className={styles.generateButton}
                data-testid="generate-spec-button"
                disabled={isArtifactActionBusy}
                onClick={handleGenerateDocument}
              >
                {specGenerateLabel}
              </button>
              <div className={styles.finishTaskActionGroup}>
                <button
                  type="button"
                  className={`${styles.confirmButton} ${isFinishTaskDisabled ? styles.finishTaskButtonDisabled : ''}`}
                  disabled={isFinishTaskDisabled}
                  data-testid="confirm-and-finish-task-button"
                  title={isFinishTaskDisabled ? finishTaskDisabledHint ?? 'Finish Task is currently unavailable.' : undefined}
                  onClick={() => {
                    setIsFinishLocked(true)
                    void handleConfirmAndFinish()
                  }}
                >
                  {isFinishActionPending ? 'Finishing...' : 'Confirm and Finish Task'}
                </button>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
