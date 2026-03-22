import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ClarifyResolutionStatus, NodeRecord } from '../../api/types'
import { useClarifyStore } from '../../stores/clarify-store'
import { useDetailStateStore } from '../../stores/detail-state-store'
import detailStyles from './NodeDetailCard.module.css'
import styles from '../graph/ClarifyMockPanel.module.css'

const RESOLUTION_OPTIONS: { value: ClarifyResolutionStatus; label: string }[] = [
  { value: 'answered', label: 'Answered' },
  { value: 'assumed', label: 'Assumed' },
  { value: 'deferred', label: 'Deferred' },
]

type Props = {
  projectId: string
  node: NodeRecord
}

export function ClarifyPanel({ projectId, node }: Props) {
  const key = `${projectId}::${node.node_id}`
  const entry = useClarifyStore((s) => s.entries[key])
  const loadClarify = useClarifyStore((s) => s.loadClarify)
  const updateDraft = useClarifyStore((s) => s.updateDraft)
  const flushAnswers = useClarifyStore((s) => s.flushAnswers)
  const confirmClarify = useClarifyStore((s) => s.confirmClarify)
  const [confirmError, setConfirmError] = useState<string | null>(null)
  const [isConfirming, setIsConfirming] = useState(false)

  useEffect(() => {
    void loadClarify(projectId, node.node_id)
  }, [projectId, node.node_id, loadClarify])

  const clarify = entry?.clarify
  const isLoading = entry?.isLoading ?? false
  const loadError = entry?.loadError ?? ''
  const saveError = entry?.saveError ?? ''
  const isSaving = entry?.isSaving ?? false
  const questions = clarify?.questions ?? []

  const allResolved = useMemo(
    () => questions.length > 0 && questions.every((q) => q.resolution_status !== 'open'),
    [questions],
  )

  const noQuestions = clarify !== undefined && questions.length === 0

  const handleDraftChange = useCallback(
    (fieldName: string, answer: string, status: ClarifyResolutionStatus) => {
      updateDraft(projectId, node.node_id, fieldName, answer, status)
    },
    [projectId, node.node_id, updateDraft],
  )

  const handleConfirm = useCallback(async () => {
    setIsConfirming(true)
    setConfirmError(null)
    try {
      await confirmClarify(projectId, node.node_id)
    } catch (error) {
      setConfirmError(error instanceof Error ? error.message : 'Confirm failed')
    } finally {
      setIsConfirming(false)
    }
  }, [projectId, node.node_id, confirmClarify])

  // Flush pending saves on unmount
  useEffect(() => {
    return () => {
      void flushAnswers(projectId, node.node_id).catch(() => undefined)
    }
  }, [projectId, node.node_id, flushAnswers])

  // Check if already confirmed
  const detailState = useDetailStateStore((s) => s.entries[key])
  const isAlreadyConfirmed = detailState?.clarify_confirmed ?? false

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

  if (noQuestions) {
    return (
      <div className={detailStyles.documentPanel}>
        <p className={detailStyles.body}>
          No unresolved task-shaping fields. All fields were resolved in the frame.
        </p>
        {!isAlreadyConfirmed ? (
          <div className={detailStyles.tabConfirmRow}>
            <button
              type="button"
              className={detailStyles.confirmButton}
              data-testid="confirm-clarify"
              onClick={handleConfirm}
              disabled={isConfirming}
            >
              {isConfirming ? 'Confirming...' : 'Confirm'}
            </button>
          </div>
        ) : null}
      </div>
    )
  }

  const canConfirm = allResolved && !isConfirming && !isSaving && !isAlreadyConfirmed

  return (
    <div className={detailStyles.documentPanel}>
      {confirmError ? (
        <div className={detailStyles.documentErrorPanel} data-testid="confirm-error-clarify">
          <p className={detailStyles.body}>{confirmError}</p>
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
              <textarea
                className={styles.customInput}
                rows={2}
                placeholder="Your answer..."
                value={q.answer}
                onChange={(e) => {
                  const val = e.target.value
                  const status: ClarifyResolutionStatus = val.trim() ? 'answered' : 'open'
                  handleDraftChange(q.field_name, val, status)
                }}
                aria-label={`Answer for: ${q.field_name}`}
                disabled={isAlreadyConfirmed}
              />
              <div className={styles.options} role="group" aria-label="Resolution status">
                {RESOLUTION_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    type="button"
                    className={`${styles.optionBtn} ${q.resolution_status === opt.value ? styles.optionBtnActive : ''}`}
                    aria-pressed={q.resolution_status === opt.value}
                    onClick={() => handleDraftChange(q.field_name, q.answer, opt.value)}
                    disabled={isAlreadyConfirmed}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      <div className={detailStyles.tabConfirmRow}>
        {isAlreadyConfirmed ? (
          <p className={styles.confirmHint} role="status">
            Clarify confirmed.
          </p>
        ) : null}
        {!isAlreadyConfirmed ? (
          <button
            type="button"
            className={detailStyles.confirmButton}
            data-testid="confirm-clarify"
            disabled={!canConfirm}
            onClick={handleConfirm}
          >
            {isConfirming ? 'Confirming...' : 'Confirm'}
          </button>
        ) : null}
      </div>
    </div>
  )
}
