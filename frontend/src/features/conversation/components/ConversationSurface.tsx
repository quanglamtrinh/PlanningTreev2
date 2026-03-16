import type { ReactNode } from 'react'

import type { ConversationRenderModel } from '../model/buildConversationRenderModel'
import styles from './ConversationSurface.module.css'

export type ConversationSurfaceConnectionState =
  | 'idle'
  | 'loading'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'error'

type Props = {
  model: ConversationRenderModel | null
  connectionState: ConversationSurfaceConnectionState
  isLoading: boolean
  errorMessage: string | null
  contextLabel?: string
  emptyTitle: string
  emptyHint: ReactNode
  showComposer?: boolean
  composerValue?: string
  composerDisabled?: boolean
  composerPlaceholder?: string
  onComposerValueChange?: (draft: string) => void
  onComposerSubmit?: () => void
}

function fallbackCopy(unsupportedPartTypes: string[]): string {
  return `Unsupported content: ${unsupportedPartTypes.join(', ')}`
}

function TypingIndicator() {
  return (
    <span className={styles.typingIndicator} aria-label="Streaming response">
      <span />
      <span />
      <span />
    </span>
  )
}

function LoadingDots() {
  return (
    <div className={styles.loadingDots} aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  )
}

export function ConversationSurface({
  model,
  connectionState,
  isLoading,
  errorMessage,
  contextLabel,
  emptyTitle,
  emptyHint,
  showComposer = false,
  composerValue = '',
  composerDisabled = false,
  composerPlaceholder = 'Write a message...',
  onComposerValueChange,
  onComposerSubmit,
}: Props) {
  const messages = model?.messages ?? []
  const showTranscript = messages.length > 0
  const canRenderComposer =
    showComposer && typeof onComposerValueChange === 'function' && typeof onComposerSubmit === 'function'
  const canSubmit = !composerDisabled && composerValue.trim().length > 0

  return (
    <div className={styles.surface}>
      <div className={styles.header}>
        <div className={styles.connectionWrap}>
          <span className={`${styles.connectionDot} ${styles[connectionState]}`} aria-hidden="true" />
          <span className={styles.connectionLabel}>{connectionState}</span>
        </div>
        {contextLabel ? <span className={styles.contextLabel}>{contextLabel}</span> : null}
      </div>

      {errorMessage ? (
        <div className={styles.errorBanner} role="alert">
          {errorMessage}
        </div>
      ) : null}

      <div className={styles.thread}>
        {!showTranscript && isLoading ? (
          <div className={styles.emptyState}>
            <LoadingDots />
            <p className={styles.emptyHint}>Loading conversation...</p>
          </div>
        ) : null}

        {!showTranscript && !isLoading ? (
          <div className={styles.emptyState}>
            <p className={styles.emptyTitle}>{emptyTitle}</p>
            <div className={styles.emptyHint}>{emptyHint}</div>
          </div>
        ) : null}

        {showTranscript
          ? messages.map((message) => {
              const showFallback = message.text.length === 0 && message.unsupportedPartTypes.length > 0
              return (
                <article
                  key={message.messageId}
                  className={`${styles.message} ${styles[message.roleTone]}`}
                >
                  <div className={styles.messageInner}>
                    <div className={styles.messageBody}>
                      {message.text}
                      {message.showTyping ? <TypingIndicator /> : null}
                      {showFallback ? (
                        <div className={styles.unsupportedFallback}>
                          {fallbackCopy(message.unsupportedPartTypes)}
                        </div>
                      ) : null}
                    </div>
                    <div className={styles.messageMeta}>
                      {message.isStreaming ? <span className={styles.streamingBadge}>streaming</span> : null}
                      {message.hasError ? <span className={styles.errorBadge}>error</span> : null}
                    </div>
                    {message.errorText ? <p className={styles.messageError}>{message.errorText}</p> : null}
                  </div>
                </article>
              )
            })
          : null}
      </div>

      {canRenderComposer ? (
        <div className={styles.composerWrap}>
          <div className={styles.composerBox}>
            <textarea
              className={styles.composer}
              rows={2}
              value={composerValue}
              placeholder={composerPlaceholder}
              disabled={composerDisabled}
              onChange={(event) => onComposerValueChange(event.target.value)}
            />
            <button
              type="button"
              className={styles.sendButton}
              disabled={!canSubmit}
              onClick={() => onComposerSubmit()}
            >
              Send
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}
