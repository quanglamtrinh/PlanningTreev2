import { useMemo, useState } from 'react'
import detailStyles from '../node/NodeDetailCard.module.css'
import styles from './ClarifyMockPanel.module.css'

type Question = {
  id: string
  label: string
  options: string[]
}

const QUESTIONS: Question[] = [
  {
    id: 'q1',
    label: 'What is the primary goal of this task?',
    options: ['Deliver a feature', 'Fix a bug', 'Improve performance'],
  },
  {
    id: 'q2',
    label: 'Who is the main stakeholder for this task?',
    options: ['Engineering', 'Product', 'Design'],
  },
  {
    id: 'q3',
    label: 'What is the expected complexity?',
    options: ['Low (< 1 day)', 'Medium (1–3 days)', 'High (> 3 days)'],
  },
]

type Answers = Record<string, string>
type CustomInputs = Record<string, string>

function optionLetter(index: number): string {
  if (index >= 0 && index < 26) {
    return String.fromCharCode(65 + index)
  }
  return String(index + 1)
}

function formatAnswerForSummary(raw: string): string {
  if (!raw) return ''
  if (raw.startsWith('__custom__')) {
    const rest = raw.slice('__custom__'.length).trim()
    return rest ? `Custom: ${rest}` : ''
  }
  return raw
}

export function ClarifyMockPanel() {
  const [answers, setAnswers] = useState<Answers>({})
  const [customInputs, setCustomInputs] = useState<CustomInputs>({})
  const [confirmed, setConfirmed] = useState(false)

  const hasAnySelection = useMemo(
    () => Object.values(answers).some((v) => v && v.trim().length > 0),
    [answers],
  )

  const selectionSummary = useMemo(() => {
    const parts: string[] = []
    for (const q of QUESTIONS) {
      const raw = answers[q.id]
      if (!raw) continue
      const display = formatAnswerForSummary(raw)
      if (display) {
        parts.push(`${q.label} → ${display}`)
      }
    }
    if (parts.length === 0) {
      return 'No selections yet — choose options or add a short note below.'
    }
    return parts.join(' · ')
  }, [answers])

  function handleOptionClick(questionId: string, option: string) {
    setCustomInputs((prev) => {
      const next = { ...prev }
      delete next[questionId]
      return next
    })
    setAnswers((prev) =>
      prev[questionId] === option ? { ...prev, [questionId]: '' } : { ...prev, [questionId]: option },
    )
  }

  function handleCustomInput(questionId: string, value: string) {
    setCustomInputs((prev) => ({ ...prev, [questionId]: value }))
    if (value.trim()) {
      setAnswers((prev) => ({ ...prev, [questionId]: `__custom__${value}` }))
    } else {
      setAnswers((prev) => {
        const next = { ...prev }
        delete next[questionId]
        return next
      })
    }
  }

  const canConfirm = hasAnySelection && !confirmed

  return (
    <div className={detailStyles.documentPanel}>
      <div
        className={styles.selectionSummary}
        role="region"
        aria-label="Current clarify selections"
        aria-live="polite"
      >
        <span className={styles.selectionSummaryLabel}>Current selections</span>
        <p className={styles.selectionSummaryText}>{selectionSummary}</p>
      </div>

      <div className={styles.clarifyBody}>
        {QUESTIONS.map((q, idx) => (
          <div key={q.id}>
            {idx > 0 && <div className={styles.divider} />}
            <div className={styles.question}>
              <p className={styles.questionLabel} id={`clarify-q-${q.id}`}>
                <span className={styles.questionIndex}>{idx + 1}</span>
                {q.label}
              </p>
              <div className={styles.options} role="group" aria-labelledby={`clarify-q-${q.id}`}>
                {q.options.map((opt, oi) => {
                  const selected = answers[q.id] === opt
                  return (
                    <button
                      key={opt}
                      type="button"
                      className={`${styles.optionBtn} ${selected ? styles.optionBtnActive : ''}`}
                      aria-pressed={selected}
                      onClick={() => handleOptionClick(q.id, opt)}
                    >
                      <span className={styles.optionLetter} aria-hidden="true">
                        {optionLetter(oi)}
                      </span>
                      <span className={styles.optionBtnBody}>{opt}</span>
                    </button>
                  )
                })}
              </div>
              <textarea
                className={styles.customInput}
                rows={2}
                placeholder="Or describe in your own words…"
                value={customInputs[q.id] ?? ''}
                onChange={(e) => handleCustomInput(q.id, e.target.value)}
                aria-label={`Additional notes for: ${q.label}`}
              />
            </div>
          </div>
        ))}
      </div>

      <div className={detailStyles.tabConfirmRow}>
        <div className={styles.confirmRowInner}>
          {confirmed ? (
            <p className={styles.confirmHint} role="status">
              Clarify answers confirmed.
            </p>
          ) : (
            <span className={styles.confirmHintSpacer} aria-hidden />
          )}
          <button
            type="button"
            className={detailStyles.confirmButton}
            data-testid="confirm-clarify"
            disabled={!canConfirm}
            title={!hasAnySelection ? 'Choose at least one answer before confirming' : undefined}
            onClick={() => setConfirmed(true)}
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}
