import { useState } from 'react'
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

export function ClarifyMockPanel() {
  const [answers, setAnswers] = useState<Answers>({})
  const [customInputs, setCustomInputs] = useState<CustomInputs>({})
  const [confirmed, setConfirmed] = useState(false)

  function handleOptionClick(questionId: string, option: string) {
    setAnswers((prev) =>
      prev[questionId] === option
        ? { ...prev, [questionId]: '' }
        : { ...prev, [questionId]: option },
    )
  }

  function handleCustomInput(questionId: string, value: string) {
    setCustomInputs((prev) => ({ ...prev, [questionId]: value }))
    if (value.trim()) {
      setAnswers((prev) => ({ ...prev, [questionId]: `__custom__${value}` }))
    }
  }

  return (
    <div className={detailStyles.documentPanel}>
      <div className={styles.clarifyBody}>
        {QUESTIONS.map((q, idx) => (
          <div key={q.id}>
            {idx > 0 && <div className={styles.divider} />}
            <div className={styles.question}>
              <p className={styles.questionLabel}>
                <span className={styles.questionIndex}>{idx + 1}</span>
                {q.label}
              </p>
              <div className={styles.options}>
                {q.options.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    className={`${styles.optionBtn} ${answers[q.id] === opt ? styles.optionBtnActive : ''}`}
                    onClick={() => handleOptionClick(q.id, opt)}
                  >
                    {opt}
                  </button>
                ))}
              </div>
              <textarea
                className={styles.customInput}
                rows={2}
                placeholder="Or describe in your own words…"
                value={customInputs[q.id] ?? ''}
                onChange={(e) => handleCustomInput(q.id, e.target.value)}
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
            onClick={() => setConfirmed(true)}
          >
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}
