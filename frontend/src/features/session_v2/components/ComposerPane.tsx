import { useEffect, useMemo, useRef, useState } from 'react'
import type { ClipboardEvent, KeyboardEvent } from 'react'

export type ComposerAccessMode = 'full-access' | 'default-permissions'
export type ComposerEffortLevel = 'Low' | 'Medium' | 'High' | 'Extra High'
export type ComposerEffortIntent = 'low' | 'medium' | 'high' | 'extra-high'
export type ComposerWorkMode = 'local' | 'remote'
export type ComposerStreamMode = 'streaming' | 'batch'

export type ComposerRequestedPolicy = {
  model?: string | null
  accessMode?: ComposerAccessMode
  effort?: ComposerEffortIntent
  workMode?: ComposerWorkMode
  streamMode?: ComposerStreamMode
}

export type ComposerSubmitMetadata = {
  planningTree?: {
    mentionBindings?: Record<string, string>
  }
}

export type ComposerSubmitPayload = {
  input: Array<Record<string, unknown>>
  text: string
  requestedPolicy?: ComposerRequestedPolicy
  metadata?: ComposerSubmitMetadata
}

type ComposerModelOption = {
  value: string
  label: string
}

type ComposerPaneProps = {
  isTurnRunning: boolean
  disabled?: boolean
  onSubmit: (payload: ComposerSubmitPayload) => Promise<void>
  onInterrupt: () => Promise<void>
  currentCwd?: string | null
  modelOptions?: ComposerModelOption[]
  selectedModel?: string | null
  onModelChange?: (model: string) => void
  isModelLoading?: boolean
}

type ActivePopup = 'none' | 'command' | 'file' | 'skill'

type RichHistoryEntry = {
  text: string
  localImages: string[]
  remoteImages: string[]
}

const PERSISTENT_HISTORY_KEY = 'session_v2_text_history'
const PERSISTENT_HISTORY_LIMIT = 100
const SKILL_MENTIONS = [
  { label: '$researcher', path: 'skill://researcher' },
  { label: '$reviewer', path: 'skill://reviewer' },
  { label: '$worker', path: 'skill://worker' },
]
const FILE_MENTIONS = [
  { label: '@README.md', path: 'README.md' },
  { label: '@docs/', path: 'docs/' },
  { label: '@backend/', path: 'backend/' },
]
const COMMAND_SUGGESTIONS = ['/plan', '/review', '/test', '/status']
const ACCESS_MODE_LABELS: Record<ComposerAccessMode, string> = {
  'full-access': 'Full access',
  'default-permissions': 'Default permissions',
}
const EFFORT_LEVEL_VALUES: Record<ComposerEffortLevel, ComposerEffortIntent> = {
  Low: 'low',
  Medium: 'medium',
  High: 'high',
  'Extra High': 'extra-high',
}
const WORK_MODE_LABELS: Record<ComposerWorkMode, string> = {
  local: 'locally',
  remote: 'remote',
}

function loadPersistentHistory(): string[] {
  try {
    const raw = window.localStorage.getItem(PERSISTENT_HISTORY_KEY)
    if (!raw) {
      return []
    }
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }
    return parsed.filter((entry): entry is string => typeof entry === 'string')
  } catch {
    return []
  }
}

function savePersistentHistory(rows: string[]) {
  window.localStorage.setItem(PERSISTENT_HISTORY_KEY, JSON.stringify(rows.slice(0, PERSISTENT_HISTORY_LIMIT)))
}

function normalizeImageRows(localImages: string[], remoteImages: string[]): { label: string; value: string; source: 'local' | 'remote' }[] {
  const rows: { label: string; value: string; source: 'local' | 'remote' }[] = []
  let nextIndex = 1
  for (const url of remoteImages) {
    rows.push({ label: `[Image #${nextIndex}]`, value: url, source: 'remote' })
    nextIndex += 1
  }
  for (const path of localImages) {
    rows.push({ label: `[Image #${nextIndex}]`, value: path, source: 'local' })
    nextIndex += 1
  }
  return rows
}

function utf8ByteLength(value: string): number {
  let bytes = 0
  for (const char of value) {
    const codePoint = char.codePointAt(0) ?? 0
    if (codePoint <= 0x7f) {
      bytes += 1
    } else if (codePoint <= 0x7ff) {
      bytes += 2
    } else if (codePoint <= 0xffff) {
      bytes += 3
    } else {
      bytes += 4
    }
  }
  return bytes
}

function buildTextElements(
  text: string,
  bindings: Record<string, string>,
): Array<{ byteRange: { start: number; end: number }; placeholder: string }> {
  const spans: Array<{ startChar: number; endChar: number; label: string }> = []
  const labels = Object.keys(bindings)
    .filter((label) => label.length > 0 && text.includes(label))
    .sort((left, right) => right.length - left.length || left.localeCompare(right))

  for (const label of labels) {
    let cursor = 0
    while (cursor < text.length) {
      const startChar = text.indexOf(label, cursor)
      if (startChar < 0) {
        break
      }
      const endChar = startChar + label.length
      spans.push({ startChar, endChar, label })
      cursor = endChar
    }
  }

  let lastEndChar = -1
  return spans
    .sort((left, right) => left.startChar - right.startChar || right.endChar - left.endChar)
    .filter((span) => {
      if (span.startChar < lastEndChar) {
        return false
      }
      lastEndChar = span.endChar
      return true
    })
    .map((span) => {
      const start = utf8ByteLength(text.slice(0, span.startChar))
      const end = start + utf8ByteLength(text.slice(span.startChar, span.endChar))
      return {
        byteRange: { start, end },
        placeholder: span.label,
      }
    })
}

export function ComposerPane({
  isTurnRunning,
  disabled,
  onSubmit,
  onInterrupt,
  currentCwd = null,
  modelOptions = [],
  selectedModel = null,
  onModelChange,
  isModelLoading = false,
}: ComposerPaneProps) {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [draft, setDraft] = useState('')
  const [activePopup, setActivePopup] = useState<ActivePopup>('none')
  const [persistentHistory, setPersistentHistory] = useState<string[]>(() => loadPersistentHistory())
  const [localHistory, setLocalHistory] = useState<RichHistoryEntry[]>([])
  const [historyCursor, setHistoryCursor] = useState<number | null>(null)
  const [reverseSearchEnabled, setReverseSearchEnabled] = useState(false)
  const [reverseSearchQuery, setReverseSearchQuery] = useState('')
  const [reverseSearchPreview, setReverseSearchPreview] = useState<string | null>(null)
  const [localImages, setLocalImages] = useState<string[]>([])
  const [remoteImages, setRemoteImages] = useState<string[]>([])
  const [mentionBindings, setMentionBindings] = useState<Record<string, string>>({})
  const [pasteBurstUntilMs, setPasteBurstUntilMs] = useState(0)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [effortLevel, setEffortLevel] = useState<ComposerEffortLevel>('Extra High')
  const [workMode, setWorkMode] = useState<ComposerWorkMode>('local')
  const [streamMode, setStreamMode] = useState<ComposerStreamMode>('streaming')
  const [accessMode, setAccessMode] = useState<ComposerAccessMode>('full-access')

  useEffect(() => {
    savePersistentHistory(persistentHistory)
  }, [persistentHistory])

  const historyText = useMemo(() => {
    const merged = [...localHistory.map((entry) => entry.text), ...persistentHistory]
    const deduped: string[] = []
    for (const value of merged) {
      if (!value.trim()) {
        continue
      }
      if (!deduped.includes(value)) {
        deduped.push(value)
      }
    }
    return deduped
  }, [localHistory, persistentHistory])

  const imageRows = useMemo(() => normalizeImageRows(localImages, remoteImages), [localImages, remoteImages])

  useEffect(() => {
    if (reverseSearchEnabled) {
      const query = reverseSearchQuery.trim().toLowerCase()
      if (!query) {
        setReverseSearchPreview(historyText[0] ?? null)
      } else {
        const found = historyText.find((entry) => entry.toLowerCase().includes(query)) ?? null
        setReverseSearchPreview(found)
      }
      return
    }
    setReverseSearchPreview(null)
  }, [historyText, reverseSearchEnabled, reverseSearchQuery])

  function syncPopup(nextText: string) {
    if (nextText.startsWith('/')) {
      setActivePopup('command')
      return
    }
    if (nextText.includes('$')) {
      setActivePopup('skill')
      return
    }
    if (nextText.includes('@')) {
      setActivePopup('file')
      return
    }
    setActivePopup('none')
  }

  function recallHistory(step: -1 | 1) {
    if (historyText.length === 0) {
      return
    }
    const nextIndex = historyCursor === null
      ? 0
      : Math.min(Math.max(historyCursor + step, 0), historyText.length - 1)
    setHistoryCursor(nextIndex)
    const nextText = historyText[nextIndex] ?? ''
    setDraft(nextText)
    syncPopup(nextText)
  }

  function registerHistoryEntry(text: string, currentLocalImages: string[], currentRemoteImages: string[]) {
    if (!text.trim()) {
      return
    }
    setLocalHistory((previous) => [
      { text, localImages: currentLocalImages, remoteImages: currentRemoteImages },
      ...previous,
    ].slice(0, PERSISTENT_HISTORY_LIMIT))
    setPersistentHistory((previous) => [text, ...previous.filter((entry) => entry !== text)].slice(0, PERSISTENT_HISTORY_LIMIT))
  }

  function buildInputPayload(nextText: string): Array<Record<string, unknown>> {
    const normalizedText = nextText.trim()
    const input: Array<Record<string, unknown>> = []
    if (normalizedText) {
      input.push({
        type: 'text',
        text: normalizedText,
        text_elements: buildTextElements(normalizedText, mentionBindings),
      })
    }
    for (const remote of remoteImages) {
      input.push({
        type: 'image',
        url: remote,
      })
    }
    for (const localPath of localImages) {
      input.push({
        type: 'localImage',
        path: localPath,
      })
    }
    return input
  }

  async function submitNow() {
    if (disabled || isSubmitting) {
      return
    }
    const input = buildInputPayload(draft)
    if (input.length === 0) {
      return
    }
    setIsSubmitting(true)
    try {
      await onSubmit({
        input,
        text: draft,
        requestedPolicy: {
          model: selectedModel ?? null,
          accessMode,
          effort: EFFORT_LEVEL_VALUES[effortLevel],
          workMode,
          streamMode,
        },
        metadata: Object.keys(mentionBindings).length > 0
          ? { planningTree: { mentionBindings } }
          : undefined,
      })
      registerHistoryEntry(draft, localImages, remoteImages)
      setDraft('')
      setLocalImages([])
      setRemoteImages([])
      setHistoryCursor(null)
      setReverseSearchEnabled(false)
      setReverseSearchQuery('')
      setMentionBindings({})
      setActivePopup('none')
    } finally {
      setIsSubmitting(false)
    }
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'r' && event.ctrlKey) {
      event.preventDefault()
      setReverseSearchEnabled((value) => !value)
      if (reverseSearchEnabled) {
        setReverseSearchQuery('')
      }
      return
    }

    if (reverseSearchEnabled) {
      if (event.key === 'Enter') {
        event.preventDefault()
        if (reverseSearchPreview) {
          setDraft(reverseSearchPreview)
          syncPopup(reverseSearchPreview)
        }
        setReverseSearchEnabled(false)
        setReverseSearchQuery('')
      }
      return
    }

    if (event.key === 'ArrowUp' || event.key === 'ArrowDown') {
      const target = textareaRef.current
      if (!target) {
        return
      }
      const atStart = target.selectionStart === 0 && target.selectionEnd === 0
      const atEnd = target.selectionStart === draft.length && target.selectionEnd === draft.length
      if (event.key === 'ArrowUp' && atStart) {
        event.preventDefault()
        recallHistory(-1)
      }
      if (event.key === 'ArrowDown' && atEnd) {
        event.preventDefault()
        recallHistory(1)
      }
      return
    }

    if (event.key === 'Enter' && !event.shiftKey) {
      const now = Date.now()
      if (now < pasteBurstUntilMs) {
        return
      }
      event.preventDefault()
      void submitNow()
    }
  }

  function handlePaste(event: ClipboardEvent<HTMLTextAreaElement>) {
    if (navigator.userAgent.toLowerCase().includes('windows')) {
      const pasted = event.clipboardData.getData('text')
      if (pasted.length > 40 || pasted.includes('\n')) {
        setPasteBurstUntilMs(Date.now() + 500)
      }
    }
  }

  function attachLocalImage(paths: string[]) {
    if (paths.length === 0) {
      return
    }
    setLocalImages((previous) => [...previous, ...paths.filter((path) => !previous.includes(path))])
  }

  const shouldShowModelPicker = modelOptions.length > 0 || Boolean(selectedModel) || isModelLoading

  const selectedModelLabel = useMemo(() => {
    if (isModelLoading) return 'Loading...'
    if (!selectedModel) return 'Select model'
    const found = modelOptions.find((o) => o.value === selectedModel)
    return found?.label ?? selectedModel
  }, [isModelLoading, modelOptions, selectedModel])
  const cwdLabel = (currentCwd ?? '').trim()
  const hasCwdLabel = cwdLabel.length > 0

  const cycleEffort = () => {
    const levels: typeof effortLevel[] = ['Low', 'Medium', 'High', 'Extra High']
    const idx = levels.indexOf(effortLevel)
    setEffortLevel(levels[(idx + 1) % levels.length])
  }

  return (
    <section className="sessionV2Composer">
      {/* Image attachments preview */}
      {imageRows.length > 0 ? (
        <div className="sessionV2ImageRows">
          {imageRows.map((row) => (
            <div key={`${row.source}:${row.value}`} className="sessionV2ImageRow">
              <span>{row.label}</span>
              <code>{row.value}</code>
            </div>
          ))}
        </div>
      ) : null}

      {/* Reverse search overlay */}
      {reverseSearchEnabled ? (
        <div className="sessionV2ReverseSearch">
          <label>
            Reverse search
            <input
              type="text"
              value={reverseSearchQuery}
              onChange={(event) => setReverseSearchQuery(event.target.value)}
              placeholder="Search history"
            />
          </label>
          <div className="sessionV2ReversePreview">
            {reverseSearchPreview ?? 'No match'}
          </div>
        </div>
      ) : null}

      {/* Autocomplete popup */}
      {activePopup !== 'none' ? (
        <div className="sessionV2Popup">
          {activePopup === 'command' ? (
            COMMAND_SUGGESTIONS.map((command) => (
              <button
                key={command}
                type="button"
                onClick={() => {
                  const next = draft.startsWith('/') ? command : `${command} ${draft}`
                  setDraft(next)
                  setActivePopup('none')
                }}
              >
                {command}
              </button>
            ))
          ) : null}
          {activePopup === 'file' ? (
            FILE_MENTIONS.map((mention) => (
              <button
                key={mention.path}
                type="button"
                onClick={() => {
                  setDraft((previous) => `${previous} ${mention.label}`.trim())
                  setMentionBindings((previous) => ({ ...previous, [mention.label]: mention.path }))
                  setActivePopup('none')
                }}
              >
                {mention.label}
              </button>
            ))
          ) : null}
          {activePopup === 'skill' ? (
            SKILL_MENTIONS.map((mention) => (
              <button
                key={mention.path}
                type="button"
                onClick={() => {
                  setDraft((previous) => `${previous} ${mention.label}`.trim())
                  setMentionBindings((previous) => ({ ...previous, [mention.label]: mention.path }))
                  setActivePopup('none')
                }}
              >
                {mention.label}
              </button>
            ))
          ) : null}
        </div>
      ) : null}

      {/* Main card */}
      <div className="sessionV2ComposerCard">
        {/* Textarea row */}
        <div className="sessionV2ComposerTextareaRow">
          <textarea
            ref={textareaRef}
            className="sessionV2ComposerTextarea"
            value={draft}
            onChange={(event) => {
              const next = event.target.value
              setDraft(next)
              syncPopup(next)
              if (reverseSearchEnabled) {
                setReverseSearchQuery(next)
              }
            }}
            onPaste={handlePaste}
            onKeyDown={handleKeyDown}
            placeholder={isTurnRunning ? 'Steer active turn...' : 'Send a follow-up message'}
            rows={2}
            disabled={disabled || isSubmitting}
          />
        </div>

        {/* Primary action row */}
        <div className="sessionV2ComposerActionRow">
          {/* Left side */}
          <div className="sessionV2ComposerActionLeft">
            {/* Attach button */}
            <button
              type="button"
              className="sessionV2ComposerIconBtn"
              disabled={disabled || isSubmitting}
              onClick={() => fileInputRef.current?.click()}
              title="Attach photos and files"
              aria-label="Attach photos and files"
            >
              <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false" width="16" height="16">
                <path
                  d="M7 10.5L11.6 5.9C12.9 4.6 15 4.6 16.3 5.9C17.6 7.2 17.6 9.3 16.3 10.6L10.4 16.5C8.2 18.7 4.7 18.7 2.5 16.5C0.3 14.3 0.3 10.8 2.5 8.6L8.7 2.4"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>

            {/* Access level pill */}
            <button
              type="button"
              className="sessionV2ComposerPill sessionV2ComposerPillAccess"
              onClick={() => setAccessMode((prev) => prev === 'full-access' ? 'default-permissions' : 'full-access')}
              title="Toggle access mode"
            >
              <svg viewBox="0 0 16 16" width="13" height="13" fill="none" aria-hidden="true">
                <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 4v4l2.5 2.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
              {ACCESS_MODE_LABELS[accessMode]}
              <svg viewBox="0 0 10 6" width="10" height="6" aria-hidden="true" fill="none">
                <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>

            <button
              type="button"
              className="sessionV2ComposerPill sessionV2ComposerPillCwd"
              disabled={!hasCwdLabel}
              title={hasCwdLabel ? `Current cwd: ${cwdLabel}` : 'Current cwd unavailable'}
              aria-label={hasCwdLabel ? `Current cwd ${cwdLabel}` : 'Current cwd unavailable'}
            >
              <span className="sessionV2ComposerCwdPrefix">cwd</span>
              <span className="sessionV2ComposerCwdPath">{hasCwdLabel ? cwdLabel : '-'}</span>
            </button>
          </div>

          {/* Right side */}
          <div className="sessionV2ComposerActionRight">
            {/* Interrupt button (visible only when turn is running) */}
            {isTurnRunning ? (
              <button
                type="button"
                className="sessionV2ComposerPill sessionV2ComposerPillInterrupt"
                disabled={disabled || isSubmitting}
                onClick={() => void onInterrupt()}
                title="Interrupt active turn"
              >
                <svg viewBox="0 0 16 16" width="12" height="12" fill="currentColor" aria-hidden="true">
                  <rect x="3" y="3" width="10" height="10" rx="1" />
                </svg>
                Stop
              </button>
            ) : null}

            {/* Model picker */}
            {shouldShowModelPicker ? (
              <div className="sessionV2ComposerModelWrap">
                {isModelLoading ? (
                  <span className="sessionV2ComposerModelSpinner" aria-hidden="true" />
                ) : null}
                <select
                  className="sessionV2ComposerModelSelect"
                  value={selectedModel ?? ''}
                  onChange={(event) => onModelChange?.(event.target.value)}
                  disabled={disabled || isSubmitting || isModelLoading || !onModelChange}
                  aria-label="Select model"
                  title={selectedModelLabel}
                >
                  {selectedModel && !modelOptions.some((option) => option.value === selectedModel) ? (
                    <option value={selectedModel}>{selectedModel}</option>
                  ) : null}
                  {!selectedModel ? (
                    <option value="" disabled>
                      {isModelLoading ? 'Loading models...' : modelOptions.length > 0 ? 'Select model' : 'No models'}
                    </option>
                  ) : null}
                  {modelOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <span className="sessionV2ComposerModelLabel">{selectedModelLabel}</span>
                <svg className="sessionV2ComposerModelChevron" viewBox="0 0 10 6" width="9" height="9" aria-hidden="true" fill="none">
                  <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </div>
            ) : null}

            {/* Effort level */}
            <button
              type="button"
              className="sessionV2ComposerPill"
              onClick={cycleEffort}
              title="Thinking effort level"
            >
              {effortLevel}
              <svg viewBox="0 0 10 6" width="9" height="9" aria-hidden="true" fill="none">
                <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>

            {/* Mic button */}
            <button
              type="button"
              className="sessionV2ComposerIconBtn"
              disabled={disabled || isSubmitting}
              title="Voice input"
              aria-label="Voice input"
            >
              <svg viewBox="0 0 20 20" width="16" height="16" fill="none" aria-hidden="true">
                <rect x="7" y="2" width="6" height="10" rx="3" stroke="currentColor" strokeWidth="1.6" />
                <path d="M4 10a6 6 0 0012 0" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                <line x1="10" y1="16" x2="10" y2="19" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              </svg>
            </button>

            {/* Submit button */}
            <button
              type="button"
              className="sessionV2ComposerSubmitBtn"
              disabled={disabled || isSubmitting}
              onClick={() => void submitNow()}
              title={isTurnRunning ? 'Steer turn (Enter)' : 'Send (Enter)'}
              aria-label={isTurnRunning ? 'Steer turn' : 'Send'}
            >
              {isSubmitting ? (
                <span className="sessionV2ComposerSubmitSpinner" aria-hidden="true" />
              ) : (
                <svg viewBox="0 0 20 20" width="16" height="16" fill="none" aria-hidden="true">
                  <path d="M10 17V3M10 3L4 9M10 3l6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              )}
            </button>
          </div>
        </div>

        {/* Secondary row: environment toggles */}
        <div className="sessionV2ComposerEnvRow">
          <button
            type="button"
            className="sessionV2ComposerEnvPill"
            onClick={() => setWorkMode((prev) => prev === 'local' ? 'remote' : 'local')}
            title="Work environment"
          >
            <svg viewBox="0 0 16 16" width="13" height="13" fill="none" aria-hidden="true">
              <rect x="1" y="3" width="14" height="10" rx="2" stroke="currentColor" strokeWidth="1.4" />
              <path d="M5 13v1M11 13v1M3 15h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
            </svg>
            Work {WORK_MODE_LABELS[workMode]}
            <svg viewBox="0 0 10 6" width="9" height="9" aria-hidden="true" fill="none">
              <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
          <button
            type="button"
            className="sessionV2ComposerEnvPill"
            onClick={() => setStreamMode((prev) => prev === 'streaming' ? 'batch' : 'streaming')}
            title="Output mode"
          >
            <svg viewBox="0 0 16 16" width="13" height="13" fill="none" aria-hidden="true">
              <path d="M2 8h3M7 5h2M7 11h2M11 8h3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              <circle cx="5" cy="8" r="1.5" fill="currentColor" />
              <circle cx="9" cy="5" r="1.5" fill="currentColor" />
              <circle cx="9" cy="11" r="1.5" fill="currentColor" />
              <circle cx="11" cy="8" r="1.5" fill="currentColor" />
            </svg>
            {streamMode}
            <svg viewBox="0 0 10 6" width="9" height="9" aria-hidden="true" fill="none">
              <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        style={{ display: 'none' }}
        onChange={(event) => {
          const files = Array.from(event.target.files ?? [])
          attachLocalImage(
            files.map((file) => {
              const fileWithPath = file as File & { path?: string }
              return fileWithPath.path || file.name
            }),
          )
          event.currentTarget.value = ''
        }}
      />
    </section>
  )
}
