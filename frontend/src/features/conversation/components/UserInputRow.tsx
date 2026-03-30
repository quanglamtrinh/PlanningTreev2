import { useEffect, useMemo, useState } from 'react'
import type { PendingUserInputRequest, UserInputAnswer, UserInputItem } from '../../../api/types'
import styles from './ConversationFeed.module.css'

function groupAnswersByQuestion(answers: UserInputAnswer[]): Record<string, string[]> {
  const grouped: Record<string, string[]> = {}
  for (const answer of answers) {
    grouped[answer.questionId] = [...(grouped[answer.questionId] ?? []), answer.value]
  }
  return grouped
}

export function UserInputRow({
  item,
  pendingRequest,
  onResolve,
}: {
  item: UserInputItem
  pendingRequest?: PendingUserInputRequest
  onResolve: (requestId: string, answers: UserInputAnswer[]) => Promise<void> | void
}) {
  const effectiveStatus = pendingRequest?.status ?? item.status
  const currentAnswers = pendingRequest?.answers.length ? pendingRequest.answers : item.answers
  const [draftAnswers, setDraftAnswers] = useState<Record<string, string[]>>(() =>
    groupAnswersByQuestion(currentAnswers),
  )

  useEffect(() => {
    setDraftAnswers(groupAnswersByQuestion(currentAnswers))
  }, [currentAnswers, item.id])

  const answerPayload = useMemo(() => {
    const answers: UserInputAnswer[] = []
    for (const question of item.questions) {
      const values = draftAnswers[question.id] ?? []
      if (!values.length) {
        continue
      }
      for (const value of values) {
        const matchingOption = question.options.find((option) => option.label === value || value === option.label || value === option.description)
        answers.push({
          questionId: question.id,
          value,
          label: matchingOption?.label ?? null,
        })
      }
    }
    return answers
  }, [draftAnswers, item.questions])

  const isAnswered = effectiveStatus === 'answered'
  const isSubmitting = effectiveStatus === 'answer_submitted'
  const isStale = effectiveStatus === 'stale'
  const canSubmit = effectiveStatus === 'requested' && answerPayload.length > 0

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-user-input">
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>User Input</div>
            <h3 className={styles.cardTitle}>{item.title ?? 'Additional input needed'}</h3>
          </div>
          <div className={styles.statusPill}>{effectiveStatus}</div>
        </div>

        <div className={styles.questionList}>
          {item.questions.map((question) => {
            const selectedValues = draftAnswers[question.id] ?? []
            return (
              <div key={question.id} className={styles.questionCard}>
                {question.header ? <div className={styles.questionHeader}>{question.header}</div> : null}
                <div className={styles.questionPrompt}>{question.prompt}</div>
                {question.inputType === 'text' ? (
                  <textarea
                    className={styles.textInput}
                    disabled={isAnswered || isSubmitting || isStale}
                    value={selectedValues[0] ?? ''}
                    onChange={(event) =>
                      setDraftAnswers((current) => ({
                        ...current,
                        [question.id]: event.target.value.trim() ? [event.target.value] : [],
                      }))
                    }
                  />
                ) : (
                  <div className={styles.optionList}>
                    {question.options.map((option) => {
                      const checked = selectedValues.includes(option.label)
                      const controlType = question.inputType === 'multi_select' ? 'checkbox' : 'radio'
                      return (
                        <label key={option.label} className={styles.optionLabel}>
                          <input
                            type={controlType}
                            name={question.id}
                            disabled={isAnswered || isSubmitting || isStale}
                            checked={checked}
                            onChange={(event) => {
                              const isChecked = event.target.checked
                              setDraftAnswers((current) => {
                                const existing = current[question.id] ?? []
                                if (question.inputType === 'single_select') {
                                  return {
                                    ...current,
                                    [question.id]: isChecked ? [option.label] : [],
                                  }
                                }
                                return {
                                  ...current,
                                  [question.id]: isChecked
                                    ? [...existing, option.label]
                                    : existing.filter((value) => value !== option.label),
                                }
                              })
                            }}
                          />
                          <span className={styles.optionText}>
                            <span>{option.label}</span>
                            {option.description ? (
                              <span className={styles.optionDescription}>{option.description}</span>
                            ) : null}
                          </span>
                        </label>
                      )
                    })}
                  </div>
                )}
              </div>
            )
          })}
        </div>

        {currentAnswers.length ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Current answers</div>
            <div className={styles.answerList}>
              {currentAnswers.map((answer, index) => (
                <div key={`${answer.questionId}-${answer.value}-${index}`} className={styles.answerItem}>
                  <div className={styles.subtleText}>
                    <strong>{answer.questionId}</strong>: {answer.label ?? answer.value}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {!isAnswered && !isStale ? (
          <div className={styles.actionRow}>
            <button
              type="button"
              className={styles.primaryButton}
              disabled={!canSubmit || isSubmitting}
              onClick={() => void onResolve(item.requestId, answerPayload)}
            >
              {isSubmitting ? 'Submitting…' : 'Submit answers'}
            </button>
          </div>
        ) : null}
      </div>
    </article>
  )
}
