import { useMemo, useState } from 'react'
import type { PendingServerRequest } from '../contracts'

type RequestUserInputOverlayProps = {
  request: PendingServerRequest
  onResolve: (requestId: string, result: Record<string, unknown>) => Promise<void>
  onReject: (requestId: string, reason?: string | null) => Promise<void>
}

type InputQuestionOption = {
  label: string
  description?: string
  value?: string
}

type InputQuestion = {
  id: string
  question: string
  options?: InputQuestionOption[]
}

function parseQuestions(payload: Record<string, unknown>): InputQuestion[] {
  const raw = payload.questions
  if (!Array.isArray(raw)) {
    return []
  }
  const questions: InputQuestion[] = []
  for (const row of raw) {
    if (!row || typeof row !== 'object') {
      continue
    }
    const record = row as Record<string, unknown>
    const id = String(record.id ?? '').trim()
    const question = String(record.question ?? '').trim()
    if (!id || !question) {
      continue
    }
    const rawOptions = Array.isArray(record.options) ? record.options : []
    const options: InputQuestionOption[] = rawOptions
      .filter((option): option is Record<string, unknown> => Boolean(option) && typeof option === 'object')
      .map((option) => ({
        label: String(option.label ?? ''),
        description: typeof option.description === 'string' ? option.description : undefined,
        value: typeof option.value === 'string' ? option.value : undefined,
      }))
      .filter((option) => option.label.trim().length > 0)
    questions.push({
      id,
      question,
      options: options.length > 0 ? options : undefined,
    })
  }
  return questions
}

export function RequestUserInputOverlay({
  request,
  onResolve,
  onReject,
}: RequestUserInputOverlayProps) {
  const questions = useMemo(() => parseQuestions(request.payload), [request.payload])
  const [activeIndex, setActiveIndex] = useState(0)
  const [selectedByQuestionId, setSelectedByQuestionId] = useState<Record<string, number>>({})
  const [notesByQuestionId, setNotesByQuestionId] = useState<Record<string, string>>({})
  const [isSubmitting, setIsSubmitting] = useState(false)

  const activeQuestion = questions[activeIndex] ?? null
  const activeSelection = activeQuestion ? selectedByQuestionId[activeQuestion.id] ?? 0 : 0
  const activeNotes = activeQuestion ? notesByQuestionId[activeQuestion.id] ?? '' : ''

  async function handleSubmit() {
    setIsSubmitting(true)
    try {
      const answers = questions.map((question) => {
        const selectedIndex = selectedByQuestionId[question.id] ?? 0
        const selectedOption = question.options?.[selectedIndex]
        const notes = (notesByQuestionId[question.id] ?? '').trim()
        return {
          id: question.id,
          question: question.question,
          selectedOption: selectedOption?.value ?? selectedOption?.label ?? null,
          notes: notes.length > 0 ? notes : null,
          status: selectedOption || notes.length > 0 ? 'answered' : 'skipped',
        }
      })
      await onResolve(request.requestId, { answers })
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="sessionV2Overlay">
      <div className="sessionV2OverlayCard">
        <header className="sessionV2OverlayHeader">
          <h3>Request user input</h3>
          <p>Question {Math.min(activeIndex + 1, Math.max(questions.length, 1))}/{Math.max(questions.length, 1)}</p>
        </header>
        {activeQuestion ? (
          <div className="sessionV2OverlayBody">
            <div className="sessionV2Question">{activeQuestion.question}</div>
            {activeQuestion.options ? (
              <div className="sessionV2Options">
                {activeQuestion.options.map((option, index) => (
                  <button
                    key={`${activeQuestion.id}:${option.label}:${index}`}
                    type="button"
                    className={activeSelection === index ? 'sessionV2Option active' : 'sessionV2Option'}
                    onClick={() => {
                      setSelectedByQuestionId((previous) => ({ ...previous, [activeQuestion.id]: index }))
                    }}
                  >
                    <span>{option.label}</span>
                    {option.description ? <small>{option.description}</small> : null}
                  </button>
                ))}
              </div>
            ) : null}
            <textarea
              className="sessionV2OverlayNotes"
              value={activeNotes}
              onChange={(event) => {
                const next = event.target.value
                setNotesByQuestionId((previous) => ({ ...previous, [activeQuestion.id]: next }))
              }}
              placeholder="Add notes (optional)"
              rows={4}
            />
          </div>
        ) : (
          <div className="sessionV2OverlayBody">
            <p>This request has no structured questions. You can continue or cancel.</p>
          </div>
        )}
        <footer className="sessionV2OverlayFooter">
          <div className="sessionV2OverlayNav">
            <button type="button" disabled={activeIndex <= 0 || isSubmitting} onClick={() => setActiveIndex((value) => Math.max(0, value - 1))}>
              Prev
            </button>
            <button
              type="button"
              disabled={activeIndex >= questions.length - 1 || isSubmitting}
              onClick={() => setActiveIndex((value) => Math.min(questions.length - 1, value + 1))}
            >
              Next
            </button>
          </div>
          <div className="sessionV2OverlayActions">
            <button type="button" disabled={isSubmitting} onClick={() => void onReject(request.requestId, 'cancel')}>
              Cancel
            </button>
            <button type="button" disabled={isSubmitting} onClick={() => void handleSubmit()}>
              Submit
            </button>
          </div>
        </footer>
      </div>
    </div>
  )
}
