import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { GenJobStatus, NodeRecord } from '../../api/types'
import { api, ApiError } from '../../api/client'
import { useClarifyStore } from '../../stores/clarify-store'
import { useDetailStateStore } from '../../stores/detail-state-store'
import { useNodeDocumentStore } from '../../stores/node-document-store'
import detailStyles from './NodeDetailCard.module.css'
import styles from '../graph/ClarifyMockPanel.module.css'

type Props = {
  projectId: string
  node: NodeRecord
  readOnly?: boolean
}

export function ClarifyPanel({ projectId, node, readOnly }: Props) {
  const key = `${projectId}::${node.node_id}`
  const entry = useClarifyStore((s) => s.entries[key])
  const loadClarify = useClarifyStore((s) => s.loadClarify)
  const invalidateClarify = useClarifyStore((s) => s.invalidateEntry)
  const selectOption = useClarifyStore((s) => s.selectOption)
  const updateCustomAnswer = useClarifyStore((s) => s.updateCustomAnswer)
  const flushAnswers = useClarifyStore((s) => s.flushAnswers)
  const confirmClarify = useClarifyStore((s) => s.confirmClarify)
  const invalidateFrameDoc = useNodeDocumentStore((s) => s.invalidateEntry)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [isConfirming, setIsConfirming] = useState(false)
  const loadDetailState = useDetailStateStore((s) => s.loadDetailState)
  const [genStatus, setGenStatus] = useState<GenJobStatus>('idle')
  const [genError, setGenError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof globalThis.setInterval> | undefined>(undefined)

  const isGenerating = genStatus === 'active'

  // ── Document load ───────────────────────────────────────────

  useEffect(() => {
    void loadClarify(projectId, node.node_id)
  }, [projectId, node.node_id, loadClarify])

  // ── Generation: polling, recovery, trigger ──────────────────

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current !== undefined) {
        globalThis.clearInterval(pollRef.current)
      }
    }
  }, [])

  const startPolling = useCallback(() => {
    if (pollRef.current !== undefined) return
    pollRef.current = globalThis.setInterval(() => {
      void api.getClarifyGenStatus(projectId, node.node_id).then((status) => {
        if (status.status !== 'active') {
          if (pollRef.current !== undefined) {
            globalThis.clearInterval(pollRef.current)
            pollRef.current = undefined
          }
          setGenStatus(status.status)
          if (status.status === 'failed') {
            setGenError(status.error ?? 'Generation failed')
          } else {
            // Reload clarify data and detail state after successful generation.
            // Detail state refresh is needed because zero-question generation
            // auto-confirms clarify on the backend, which unlocks the Spec tab.
            invalidateClarify(projectId, node.node_id)
            void loadClarify(projectId, node.node_id)
            void loadDetailState(projectId, node.node_id)
          }
        }
      }).catch(() => {
        // Keep polling on transient errors
      })
    }, 2000)
  }, [projectId, node.node_id, invalidateClarify, loadClarify, loadDetailState])

  // Recover generation status on mount
  useEffect(() => {
    let cancelled = false
    void api.getClarifyGenStatus(projectId, node.node_id).then((status) => {
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
  }, [projectId, node.node_id, startPolling])

  const handleGenerate = useCallback(async () => {
    setGenError(null)
    try {
      // Flush any pending answer drafts before generation overwrites clarify.json.
      // If flush fails, abort — unsaved answers must not be overwritten.
      await flushAnswers(projectId, node.node_id)
    } catch {
      setGenError('Could not save pending answers. Resolve the save error before generating.')
      return
    }
    setGenStatus('active')
    try {
      await api.generateClarify(projectId, node.node_id)
      startPolling()
    } catch (error) {
      // If a job is already active (e.g. started from another tab), attach to it
      if (error instanceof ApiError && error.code === 'clarify_generation_not_allowed') {
        startPolling()
        return
      }
      setGenStatus('failed')
      setGenError(error instanceof Error ? error.message : 'Generate failed')
    }
  }, [projectId, node.node_id, flushAnswers, startPolling])

  // ── Derived state ───────────────────────────────────────────

  const clarify = entry?.clarify
  const isLoading = entry?.isLoading ?? false
  const loadError = entry?.loadError ?? ''
  const saveError = entry?.saveError ?? ''
  const isSaving = entry?.isSaving ?? false
  const questions = clarify?.questions ?? []

  const allResolved = useMemo(
    () =>
      questions.length > 0 &&
      questions.every(
        (q) => q.selected_option_id != null || q.custom_answer.trim() !== '',
      ),
    [questions],
  )

  const noQuestions = clarify !== undefined && questions.length === 0

  const handleApplyToFrame = useCallback(async () => {
    setIsConfirming(true)
    setConfirmError(null)
    try {
      await confirmClarify(projectId, node.node_id)
      // Invalidate frame document cache so the editor reloads the patched frame.md
      invalidateFrameDoc(projectId, node.node_id, 'frame')
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Apply failed')
    } finally {
      setIsConfirming(false)
    }
  }, [projectId, node.node_id, confirmClarify, invalidateFrameDoc])

  // Flush pending saves on unmount
  useEffect(() => {
    return () => {
      void flushAnswers(projectId, node.node_id).catch(() => undefined)
    }
  }, [projectId, node.node_id, flushAnswers])

  // Check if already confirmed or read-only
  const detailState = useDetailStateStore((s) => s.entries[key])
  const isAlreadyConfirmed = detailState?.clarify_confirmed ?? false
  const isDisabled = readOnly || isAlreadyConfirmed

  // ── Generating state ────────────────────────────────────────

  if (isGenerating) {
    return (
      <div className={detailStyles.documentPanel}>
        <p className={detailStyles.body} data-testid="clarify-generating">
          Generating clarify questions...
        </p>
      </div>
    )
  }

  // ── Loading state ───────────────────────────────────────────

  if (isLoading && !clarify) {
    return (
      <div className={detailStyles.documentPanel}>
        <p className={detailStyles.body}>Loading clarify questions...</p>
      </div>
    )
  }

  if (loadError && !clarify) {
    return (
      <div className={detailStyles.documentPanel}>
        <div className={detailStyles.documentErrorPanel}>
          <p className={detailStyles.body}>{loadError}</p>
          <button
            type="button"
            className={detailStyles.retryButton}
            onClick={() => void loadClarify(projectId, node.node_id)}
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  // ── No questions state ──────────────────────────────────────

  if (noQuestions) {
    return (
      <div className={detailStyles.documentPanel}>
        {genError ? (
          <div className={detailStyles.documentErrorPanel} data-testid="generate-error-clarify">
            <p className={detailStyles.body}>{genError}</p>
          </div>
        ) : null}
        <p className={detailStyles.body}>
          No unresolved task-shaping fields. All fields were resolved in the frame.
        </p>
        {!isDisabled ? (
          <div className={detailStyles.tabConfirmRow}>
            <button
              type="button"
              className={detailStyles.generateButton}
              data-testid="generate-clarify-button"
              disabled={isConfirming}
              onClick={handleGenerate}
            >
              Generate Questions
            </button>
            <button
              type="button"
              className={detailStyles.confirmButton}
              data-testid="confirm-clarify"
              onClick={handleApplyToFrame}
              disabled={isConfirming}
            >
              {isConfirming ? 'Applying...' : 'Apply to Frame'}
            </button>
          </div>
        ) : null}
      </div>
    )
  }

  // ── Questions state ─────────────────────────────────────────

  const canConfirm = allResolved && !isConfirming && !isSaving && !isDisabled && !isGenerating

  return (
    <div className={detailStyles.documentPanel}>
      {confirmError ? (
        <div className={detailStyles.documentErrorPanel} data-testid="confirm-error-clarify">
          <p className={detailStyles.body}>{confirmError}</p>
        </div>
      ) : null}

      {genError ? (
        <div className={detailStyles.documentErrorPanel} data-testid="generate-error-clarify">
          <p className={detailStyles.body}>{genError}</p>
        </div>
      ) : null}

      {saveError ? (
        <div className={detailStyles.documentErrorPanel} data-testid="save-error-clarify">
          <p className={detailStyles.body}>Save failed: {saveError}</p>
        </div>
      ) : null}

      <div className={styles.clarifyBody}>
        {questions.map((q, idx) => (
          <div key={q.field_name}>
            {idx > 0 && <div className={styles.divider} />}
            <div className={styles.question}>
              <p className={styles.questionLabel} id={`clarify-q-${q.field_name}`}>
                <span className={styles.questionIndex}>{idx + 1}</span>
                {q.question}
              </p>
              {q.why_it_matters ? (
                <p className={styles.whyItMatters}>{q.why_it_matters}</p>
              ) : null}
              {q.current_value ? (
                <p className={styles.whyItMatters}>
                  Current value: <strong>{q.current_value}</strong>
                </p>
              ) : null}

              {/* Options as pill buttons */}
              {q.options.length > 0 ? (
                <div className={styles.options} role="group" aria-label="Options">
                  {q.options.map((opt) => (
                    <button
                      key={opt.id}
                      type="button"
                      className={`${styles.optionBtn} ${q.selected_option_id === opt.id ? styles.optionBtnActive : ''}`}
                      aria-pressed={q.selected_option_id === opt.id}
                      onClick={() => {
                        const newId = q.selected_option_id === opt.id ? null : opt.id
                        selectOption(projectId, node.node_id, q.field_name, newId)
                      }}
                      disabled={isDisabled}
                    >
                      {opt.label}
                      {opt.recommended ? (
                        <span className={styles.recommendedBadge}> (Recommended)</span>
                      ) : null}
                    </button>
                  ))}
                </div>
              ) : null}

              {q.options.length > 0 && q.selected_option_id ? (
                (() => {
                  const selected = q.options.find((o) => o.id === q.selected_option_id)
                  return selected?.rationale ? (
                    <p className={styles.optionRationale}>{selected.rationale}</p>
                  ) : null
                })()
              ) : null}

              {/* Custom answer textarea */}
              {q.allow_custom ? (
                <textarea
                  className={styles.customInput}
                  rows={2}
                  placeholder="Or describe in your own words..."
                  value={q.custom_answer}
                  onChange={(e) => {
                    updateCustomAnswer(projectId, node.node_id, q.field_name, e.target.value)
                  }}
                  aria-label={`Custom answer for: ${q.field_name}`}
                  disabled={isDisabled}
                />
              ) : null}
            </div>
          </div>
        ))}
      </div>

      <div className={detailStyles.tabConfirmRow}>
        {isDisabled ? (
          <p className={styles.confirmHint} role="status">
            {isAlreadyConfirmed ? 'Clarify confirmed.' : 'Read-only.'}
          </p>
        ) : (
          <>
            <button
              type="button"
              className={detailStyles.generateButton}
              data-testid="generate-clarify-button"
              disabled={isConfirming || isGenerating}
              onClick={handleGenerate}
            >
              Regenerate Questions
            </button>
            <button
              type="button"
              className={detailStyles.confirmButton}
              data-testid="confirm-clarify"
              disabled={!canConfirm}
              onClick={handleApplyToFrame}
            >
              {isConfirming ? 'Applying...' : 'Apply to Frame'}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
