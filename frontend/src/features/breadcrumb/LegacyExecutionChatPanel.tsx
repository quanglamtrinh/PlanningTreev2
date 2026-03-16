import { useEffect, useMemo, useRef } from 'react'
import type { ReactNode } from 'react'

import type { NodeRecord } from '../../api/types'
import { useChatStore } from '../../stores/chat-store'
import styles from './ChatPanel.module.css'

type Props = {
  node: NodeRecord
  projectId: string
  composerEnabled?: boolean
  composerPlaceholder?: string
  emptyTitle?: string
  emptyHint?: ReactNode
}

function formatTimestamp(value: string) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return 'now'
  }
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function SendIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M10.5 12H5L3.28 4.35A1 1 0 0 1 4.26 3.2l15.5 7.74a1 1 0 0 1 0 1.79l-15.5 7.74a1 1 0 0 1-.98-1.15L5 12"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="4" y="4" width="16" height="16" rx="3" fill="currentColor" />
    </svg>
  )
}

function ResetIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M3 3v5h5" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export function LegacyExecutionChatPanel({
  node,
  projectId,
  composerEnabled = true,
  composerPlaceholder,
  emptyTitle = 'Start the conversation',
  emptyHint,
}: Props) {
  const session = useChatStore((state) => state.session)
  const composerDraft = useChatStore((state) => state.composerDraft)
  const connectionStatus = useChatStore((state) => state.connectionStatus)
  const isLoadingSession = useChatStore((state) => state.isLoadingSession)
  const isSendingMessage = useChatStore((state) => state.isSendingMessage)
  const error = useChatStore((state) => state.error)
  const setComposerDraft = useChatStore((state) => state.setComposerDraft)
  const sendMessage = useChatStore((state) => state.sendMessage)
  const resetSession = useChatStore((state) => state.resetSession)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)

  const lastMessageKey = useMemo(() => {
    if (!session || session.messages.length === 0) {
      return ''
    }
    const lastMessage = session.messages[session.messages.length - 1]
    return `${lastMessage.message_id}:${lastMessage.updated_at}:${lastMessage.content.length}`
  }, [session])

  useEffect(() => {
    const textarea = composerRef.current
    if (!textarea) {
      return
    }
    textarea.style.height = 'auto'
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
  }, [composerDraft])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lastMessageKey, session?.active_turn_id])

  const isBusy = Boolean(session?.active_turn_id || isSendingMessage)
  const canSend =
    composerEnabled &&
    connectionStatus === 'connected' &&
    composerDraft.trim().length > 0 &&
    !session?.active_turn_id &&
    !isSendingMessage
  const canReset = Boolean(session) && !session?.active_turn_id && !isSendingMessage

  async function handleSend() {
    if (!canSend) {
      return
    }
    try {
      await sendMessage(projectId, node.node_id, composerDraft)
    } catch {
      return
    }
  }

  async function handleReset() {
    if (!canReset) {
      return
    }
    const confirmed = window.confirm('Reset this chat session and clear all messages?')
    if (!confirmed) {
      return
    }
    try {
      await resetSession(projectId, node.node_id)
    } catch {
      return
    }
  }

  return (
    <div className={styles.panel}>
      <div className={styles.statusBar}>
        <span className={`${styles.dot} ${styles[connectionStatus]}`} aria-hidden="true" />
        <span className={styles.statusLabel}>{connectionStatus}</span>
        <span className={styles.nodeLabel}>
          {node.hierarchical_number} / {node.title}
        </span>
        <button
          type="button"
          className={styles.resetBtn}
          disabled={!canReset}
          title="Reset session"
          onClick={() => void handleReset()}
        >
          <ResetIcon />
          <span>Reset</span>
        </button>
      </div>

      {error ? <div className={styles.errorBanner}>{error}</div> : null}

      <div className={styles.thread}>
        {isLoadingSession ? (
          <div className={styles.emptyState}>
            <div className={styles.loadingDots}>
              <span />
              <span />
              <span />
            </div>
            <p>Loading conversation...</p>
          </div>
        ) : null}

        {!isLoadingSession && session?.messages.length === 0 ? (
          <div className={styles.emptyState}>
            <div className={styles.emptyIcon} aria-hidden="true">
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none">
                <path
                  d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </div>
            <p className={styles.emptyTitle}>{emptyTitle}</p>
            <p className={styles.emptyHint}>
              {emptyHint ?? (
                <>
                  Ask a question or give an instruction to begin working through <strong>{node.title}</strong>.
                </>
              )}
            </p>
          </div>
        ) : null}

        {session?.messages.map((message) => (
          <article
            key={message.message_id}
            className={`${styles.message} ${
              message.role === 'assistant' ? styles.assistantMessage : styles.userMessage
            }`}
          >
            {message.role === 'assistant' ? (
              <div className={styles.assistantAvatar} aria-hidden="true">
                AI
              </div>
            ) : null}

            <div className={styles.messageInner}>
              <div className={styles.messageBody}>
                {message.content ||
                  (isBusy ? (
                    <span className={styles.typingIndicator}>
                      <span />
                      <span />
                      <span />
                    </span>
                  ) : (
                    ''
                  ))}
              </div>
              <div className={styles.messageMeta}>
                {message.status === 'streaming' ? <span className={styles.streamingBadge}>streaming</span> : null}
                {message.status === 'error' ? <span className={styles.errorBadge}>error</span> : null}
                <span className={styles.timestamp}>{formatTimestamp(message.updated_at)}</span>
              </div>
              {message.error ? <p className={styles.messageError}>{message.error}</p> : null}
            </div>
          </article>
        ))}

        <div ref={endRef} />
      </div>

      <div className={styles.composerWrap}>
        <div className={`${styles.composerBox} ${isBusy ? styles.composerBusy : ''}`}>
          <textarea
            ref={composerRef}
            className={styles.composer}
            rows={1}
            value={composerDraft}
            placeholder={
              composerPlaceholder ??
              (connectionStatus === 'connected' ? `Message ${node.title}...` : 'Waiting for connection...')
            }
            disabled={connectionStatus !== 'connected' || !composerEnabled}
            onChange={(event) => setComposerDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                void handleSend()
              }
            }}
          />
          <button
            type="button"
            className={`${styles.sendBtn} ${canSend ? styles.sendBtnActive : ''}`}
            disabled={!canSend && !isBusy}
            aria-label={isBusy ? 'Stop generation' : 'Send message'}
            onClick={() => void handleSend()}
          >
            {isBusy ? <StopIcon /> : <SendIcon />}
          </button>
        </div>
        <p className={styles.hint}>
          <kbd>Enter</kbd> to send / <kbd>Shift+Enter</kbd> for new line
        </p>
      </div>
    </div>
  )
}
