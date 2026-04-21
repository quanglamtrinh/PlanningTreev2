import { useEffect, useMemo, useRef, useState } from 'react'
import type { ClipboardEvent, KeyboardEvent } from 'react'

type ComposerSubmitPayload = {
  input: Array<Record<string, unknown>>
  text: string
}

type ComposerPaneProps = {
  isTurnRunning: boolean
  disabled?: boolean
  onSubmit: (payload: ComposerSubmitPayload) => Promise<void>
  onInterrupt: () => Promise<void>
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

export function ComposerPane({ isTurnRunning, disabled, onSubmit, onInterrupt }: ComposerPaneProps) {
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
  const [remoteImageInput, setRemoteImageInput] = useState('')
  const [mentionBindings, setMentionBindings] = useState<Record<string, string>>({})
  const [pasteBurstUntilMs, setPasteBurstUntilMs] = useState(0)
  const [isSubmitting, setIsSubmitting] = useState(false)

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
        mentionBindings,
      })
    }
    for (const remote of remoteImages) {
      input.push({
        type: 'image',
        imageUrl: remote,
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
      await onSubmit({ input, text: draft })
      registerHistoryEntry(draft, localImages, remoteImages)
      setDraft('')
      setLocalImages([])
      setRemoteImages([])
      setRemoteImageInput('')
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

  return (
    <section className="sessionV2Composer">
      <div className="sessionV2ComposerHeader">
        <div className="sessionV2ComposerBadges">
          <span>{isTurnRunning ? 'turn: running' : 'turn: idle'}</span>
          <span>popup: {activePopup}</span>
          <span>history: {historyText.length}</span>
        </div>
        <div className="sessionV2ComposerActions">
          <button type="button" disabled={disabled || isSubmitting} onClick={() => fileInputRef.current?.click()}>
            Attach file
          </button>
          <button type="button" disabled={disabled || isSubmitting || !isTurnRunning} onClick={() => void onInterrupt()}>
            Interrupt
          </button>
        </div>
      </div>

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

      <textarea
        ref={textareaRef}
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
        placeholder={isTurnRunning ? 'Steer active turn...' : 'Start new turn...'}
        rows={4}
        disabled={disabled || isSubmitting}
      />

      <div className="sessionV2ComposerFooter">
        <div className="sessionV2ImageInput">
          <input
            type="text"
            value={remoteImageInput}
            onChange={(event) => setRemoteImageInput(event.target.value)}
            placeholder="Remote image URL"
            disabled={disabled || isSubmitting}
          />
          <button
            type="button"
            disabled={disabled || isSubmitting || remoteImageInput.trim().length === 0}
            onClick={() => {
              const next = remoteImageInput.trim()
              if (!next) {
                return
              }
              setRemoteImages((previous) => [...previous, next])
              setRemoteImageInput('')
            }}
          >
            Add URL
          </button>
        </div>
        <button type="button" disabled={disabled || isSubmitting} onClick={() => void submitNow()}>
          {isTurnRunning ? 'Steer (Enter)' : 'Send (Enter)'}
        </button>
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
