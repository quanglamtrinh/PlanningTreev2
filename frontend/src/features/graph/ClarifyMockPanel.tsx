import { useState } from 'react'
import styles from './ClarifyMockPanel.module.css'

// ─── Mock data ──────────────────────────────────────────────────────────────

type Option = {
  id: string
  label: string
  hint?: string
}

type Question = {
  id: string
  text: string
  options: Option[]
}

const MOCK_QUESTIONS: Question[] = [
  {
    id: 'q1',
    text: 'Bạn muốn PlanningTree đi theo mô hình auth nào cho project/app này?',
    options: [
      { id: 'q1-1', label: 'Local stub (Recommended)', hint: 'Không cần backend auth, dùng mock user' },
      { id: 'q1-2', label: 'Local lock', hint: 'Auth chỉ trong môi trường local' },
      { id: 'q1-3', label: 'OAuth2 cloud', hint: 'Tích hợp OAuth2 với provider bên ngoài' },
    ],
  },
  {
    id: 'q2',
    text: 'Cấu trúc thư mục nào phù hợp nhất cho module này?',
    options: [
      { id: 'q2-1', label: 'Feature-based (Recommended)', hint: 'Mỗi feature một thư mục riêng' },
      { id: 'q2-2', label: 'Layer-based', hint: 'Tách theo layer: components, hooks, services' },
      { id: 'q2-3', label: 'Flat', hint: 'Tất cả file ở cùng một cấp' },
    ],
  },
  {
    id: 'q3',
    text: 'Chiến lược deploy nào bạn muốn agent ưu tiên?',
    options: [
      { id: 'q3-1', label: 'Docker + Compose (Recommended)', hint: 'Container hóa toàn bộ stack' },
      { id: 'q3-2', label: 'Bare metal / systemd', hint: 'Deploy trực tiếp lên server' },
      { id: 'q3-3', label: 'Cloud PaaS (Render / Railway)', hint: 'Push-to-deploy qua platform' },
    ],
  },
]

// ─── QuestionCard ─────────────────────────────────────────────────────────────

function QuestionCard({ question, index }: { question: Question; index: number }) {
  const [selected, setSelected] = useState<string | null>(null)
  const [customDraft, setCustomDraft] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [hovered, setHovered] = useState<string | null>(null)

  const CUSTOM_ID = `${question.id}-custom`
  const isCustomSelected = selected === CUSTOM_ID

  function handleSelect(id: string) {
    if (submitted) return
    setSelected(id)
  }

  function handleSubmit() {
    if (!selected) return
    setSubmitted(true)
  }

  function handleDismiss() {
    setSelected(null)
    setCustomDraft('')
  }

  const canSubmit = selected !== null && (!isCustomSelected || customDraft.trim().length > 0)

  return (
    <div className={`${styles.card} ${submitted ? styles.cardDone : ''}`}>
      {/* Step indicator */}
      <p className={styles.questionStep}>Question {index + 1} of {MOCK_QUESTIONS.length}</p>

      {/* Question text */}
      <p className={styles.questionText}>{question.text}</p>

      {/* Preset options */}
      <ol className={styles.optionList}>
        {question.options.map((option, optIdx) => {
          const isSelected = selected === option.id
          return (
            <li
              key={option.id}
              className={`${styles.optionRow} ${isSelected ? styles.optionSelected : ''} ${submitted && isSelected ? styles.optionSubmitted : ''}`}
              onMouseEnter={() => setHovered(option.id)}
              onMouseLeave={() => setHovered(null)}
            >
              <button
                type="button"
                className={styles.optionBtn}
                onClick={() => handleSelect(option.id)}
                disabled={submitted}
              >
                <span className={styles.optionNum}>{optIdx + 1}.</span>
                <span className={styles.optionLabel}>{option.label}</span>
                {option.hint && (
                  <span className={styles.optionInfoWrap} title={option.hint}>
                    <svg className={styles.optionInfoIcon} viewBox="0 0 16 16" fill="none" aria-hidden="true">
                      <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.4" />
                      <path d="M8 7v4M8 5.5v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                  </span>
                )}
              </button>
              {/* Reorder arrows only on the first option */}
              {optIdx === 0 && hovered === option.id && !submitted && (
                <div className={styles.reorderGroup} aria-hidden="true">
                  <button type="button" className={styles.reorderBtn} tabIndex={-1}>↑</button>
                  <button type="button" className={styles.reorderBtn} tabIndex={-1}>↓</button>
                </div>
              )}
            </li>
          )
        })}

        {/* Custom option (option 4) */}
        <li
          className={`${styles.optionRow} ${styles.optionCustomRow} ${isCustomSelected ? styles.optionSelected : ''}`}
        >
          {isCustomSelected ? (
            <div className={styles.customExpanded}>
              <input
                autoFocus
                className={styles.customInput}
                placeholder="Mô tả yêu cầu cụ thể của bạn..."
                value={customDraft}
                onChange={(e) => setCustomDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && canSubmit) handleSubmit()
                  if (e.key === 'Escape') handleDismiss()
                }}
                disabled={submitted}
              />
              <div className={styles.customActions}>
                <button
                  type="button"
                  className={styles.dismissBtn}
                  onClick={handleDismiss}
                  disabled={submitted}
                >
                  Dismiss <kbd>ESC</kbd>
                </button>
                <button
                  type="button"
                  className={styles.submitBtn}
                  onClick={handleSubmit}
                  disabled={!canSubmit || submitted}
                >
                  Submit <kbd>↵</kbd>
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              className={styles.optionBtn}
              onClick={() => handleSelect(CUSTOM_ID)}
              disabled={submitted}
            >
              <span className={styles.optionNum}>{question.options.length + 1}.</span>
              <span className={`${styles.optionLabel} ${styles.optionLabelCustom}`}>
                No, and tell Codex what to do...
              </span>
              <div className={styles.customCollapsedActions}>
                <span className={styles.dismissLabel}>Dismiss <kbd className={styles.kbd}>ESC</kbd></span>
                <button
                  type="button"
                  className={styles.submitBtn}
                  onClick={(e) => { e.stopPropagation(); handleSelect(CUSTOM_ID) }}
                  disabled={submitted}
                >
                  Submit <kbd>↵</kbd>
                </button>
              </div>
            </button>
          )}
        </li>
      </ol>

      {/* Confirmation after submit */}
      {submitted && (
        <p className={styles.confirmedBadge}>
          ✓ Response recorded
        </p>
      )}
    </div>
  )
}

// ─── ClarifyMockPanel ─────────────────────────────────────────────────────────

export function ClarifyMockPanel({ onOpenBreadcrumb }: { onOpenBreadcrumb: () => void }) {
  return (
    <div className={styles.panel}>
      <div className={styles.panelHeader}>
        <p className={styles.panelLabel}>Clarify</p>
        <p className={styles.panelHint}>
          Answer these questions to help the agent plan more precisely.
        </p>
      </div>

      <div className={styles.questionStack}>
        {MOCK_QUESTIONS.map((question, index) => (
          <QuestionCard key={question.id} question={question} index={index} />
        ))}
      </div>

      <div className={styles.panelFooter}>
        <button type="button" className={styles.breadcrumbLink} onClick={onOpenBreadcrumb}>
          Open full conversation →
        </button>
      </div>
    </div>
  )
}
