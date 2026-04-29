import { useCallback, useId, useRef, useState, type KeyboardEvent } from 'react'
import styles from './ComposerBar.module.css'

/** Mock options for breadcrumb composer controls (UI prototype). */
const MOCK_MODELS = ['gpt-5.4', 'gpt-4.1', 'o3-mini'] as const
const MOCK_THINKING_EFFORT = ['xhigh', 'high', 'medium', 'low'] as const
const MOCK_PERMISSIONS = ['On-Request', 'Always', 'Never'] as const
const MOCK_CONTEXT_USAGE_RATIO = 0.28

type ComposerEarlyResponsePhase = 'idle' | 'pending_send' | 'stream_open' | 'first_delta'

interface ComposerBarProps {
  onSend: (content: string) => void
  disabled: boolean
  earlyResponsePhase?: ComposerEarlyResponsePhase
}

function IconListPlan() {
  return (
    <svg className={styles.pillIconSvg} width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconRobot() {
  return (
    <svg className={styles.pillIconSvg} width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <rect x="5" y="8" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="2" />
      <path d="M9 8V6a3 3 0 016 0v2" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <circle cx="10" cy="13" r="1" fill="currentColor" />
      <circle cx="14" cy="13" r="1" fill="currentColor" />
    </svg>
  )
}

function IconBrain() {
  return (
    <svg className={styles.pillIconSvg} width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 5a2.5 2.5 0 00-2.5 2.5V9a2 2 0 00-2 2v.5a2 2 0 002 2h1M12 5a2.5 2.5 0 012.5 2.5V9a2 2 0 012 2v.5a2 2 0 01-2 2h-1M9.5 13.5V18M14.5 13.5V18"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function IconShieldCheck() {
  return (
    <svg className={styles.pillIconSvg} width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M12 3l7 3v6c0 5-3.5 9-7 10-3.5-1-7-5-7-10V6l7-3z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
      <path d="M9 12l2 2 4-4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function IconChevronDown() {
  return (
    <svg className={styles.pillChevronSvg} width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M6 9l6 6 6-6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function ContextUsageRing({ ratio }: { ratio: number }) {
  const r = 7
  const c = 2 * Math.PI * r
  const clamped = Math.min(1, Math.max(0, ratio))
  const dash = clamped * c
  const label = `Context usage about ${Math.round(clamped * 100)} percent`

  return (
    <svg
      className={styles.contextRing}
      width="22"
      height="22"
      viewBox="0 0 20 20"
      role="img"
      aria-label={label}
    >
      <circle
        className={styles.contextRingTrack}
        cx="10"
        cy="10"
        r={r}
        fill="none"
        strokeWidth="2"
      />
      <circle
        className={styles.contextRingFill}
        cx="10"
        cy="10"
        r={r}
        fill="none"
        strokeWidth="2"
        strokeLinecap="round"
        transform="rotate(-90 10 10)"
        strokeDasharray={`${dash} ${c}`}
      />
    </svg>
  )
}

export function ComposerBar({ onSend, disabled, earlyResponsePhase = 'idle' }: ComposerBarProps) {
  const [text, setText] = useState('')
  const [planEnabled, setPlanEnabled] = useState(false)
  const [model, setModel] = useState<string>(MOCK_MODELS[0])
  const [thinking, setThinking] = useState<string>(MOCK_THINKING_EFFORT[0])
  const [permission, setPermission] = useState<string>(MOCK_PERMISSIONS[0])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const planId = useId()

  const handleSend = useCallback(() => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }
  }, [text, disabled, onSend])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSend()
      }
    },
    [handleSend],
  )

  const handleInput = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [])

  const earlyResponseLabel =
    earlyResponsePhase === 'pending_send'
      ? 'Sending...'
      : earlyResponsePhase === 'stream_open'
        ? 'Agent connected...'
        : earlyResponsePhase === 'first_delta'
          ? 'Responding...'
          : null

  return (
    <div className={styles.wrap} data-testid="composer">
      <div className={styles.composer}>
        <div className={styles.editorRow}>
          <textarea
            ref={textareaRef}
            className={styles.input}
            placeholder="Send a message"
            value={text}
            onChange={handleInput}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            rows={1}
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize="off"
          />
          <div className={styles.responseStatus} aria-live="polite">
            <span className={styles.responseStatusText}>{earlyResponseLabel ?? ' '}</span>
          </div>
          <button
            type="button"
            className={styles.sendBtn}
            onClick={handleSend}
            disabled={disabled || !text.trim()}
            aria-label="Send"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        </div>

        <div className={styles.controlsBar} aria-label="Composer options">
          <div className={styles.controlsLeft}>
            <label className={styles.pill} htmlFor={planId}>
              <input
                id={planId}
                type="checkbox"
                className={styles.planCheckbox}
                checked={planEnabled}
                onChange={(e) => setPlanEnabled(e.target.checked)}
              />
              <IconListPlan />
              <span className={styles.pillLabel}>Plan</span>
            </label>

            <div className={styles.pill}>
              <IconBrain />
              <select
                className={styles.pillSelect}
                value={thinking}
                onChange={(e) => setThinking(e.target.value)}
                aria-label="Thinking effort"
              >
                {MOCK_THINKING_EFFORT.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <span className={styles.pillChevron}>
                <IconChevronDown />
              </span>
            </div>

            <div className={styles.pill}>
              <IconRobot />
              <select
                className={styles.pillSelect}
                value={model}
                onChange={(e) => setModel(e.target.value)}
                aria-label="Model"
              >
                {MOCK_MODELS.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <span className={styles.pillChevron}>
                <IconChevronDown />
              </span>
            </div>

            <div className={styles.pill}>
              <IconShieldCheck />
              <select
                className={styles.pillSelect}
                value={permission}
                onChange={(e) => setPermission(e.target.value)}
                aria-label="Tool permission"
              >
                {MOCK_PERMISSIONS.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
              <span className={styles.pillChevron}>
                <IconChevronDown />
              </span>
            </div>
          </div>

          <div className={styles.controlsRight}>
            <ContextUsageRing ratio={MOCK_CONTEXT_USAGE_RATIO} />
          </div>
        </div>
      </div>
    </div>
  )
}
