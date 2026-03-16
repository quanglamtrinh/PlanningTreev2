import type { KeyboardEvent, ReactNode } from 'react'

import type { ConversationRenderModel } from '../model/buildConversationRenderModel'
import { renderConversationBlock } from './ConversationBlocks'
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
  showHeader?: boolean
  showComposer?: boolean
  composerValue?: string
  composerDisabled?: boolean
  composerPlaceholder?: string
  composerHint?: ReactNode
  onComposerValueChange?: (draft: string) => void
  onComposerSubmit?: () => void
  onComposerKeyDown?: (event: KeyboardEvent<HTMLTextAreaElement>) => void
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
  showHeader = true,
  showComposer = false,
  composerValue = '',
  composerDisabled = false,
  composerPlaceholder = 'Write a message...',
  composerHint,
  onComposerValueChange,
  onComposerSubmit,
  onComposerKeyDown,
}: Props) {
  const messages = model?.messages ?? []
  const showTranscript = messages.length > 0
  const canRenderComposer =
    showComposer && typeof onComposerValueChange === 'function' && typeof onComposerSubmit === 'function'
  const canSubmit = !composerDisabled && composerValue.trim().length > 0

  return (
    <div className={styles.surface}>
      {showHeader ? (
        <div className={styles.header}>
          <div className={styles.connectionWrap}>
            <span className={`${styles.connectionDot} ${styles[connectionState]}`} aria-hidden="true" />
            <span className={styles.connectionLabel}>{connectionState}</span>
          </div>
          {contextLabel ? <span className={styles.contextLabel}>{contextLabel}</span> : null}
        </div>
      ) : null}

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
              return (
                <article
                  key={message.messageId}
                  className={`${styles.message} ${styles[message.roleTone]}`}
                >
                  <div className={styles.messageInner}>
                    <div className={styles.messageItems}>
                      {message.items.map((item) => {
                        if (item.kind === 'assistant_text' || item.kind === 'user_text') {
                          return (
                            <div
                              key={item.key}
                              className={`${styles.messageBody} ${
                                item.kind === 'user_text' ? styles.userTextItem : styles.assistantTextItem
                              }`}
                            >
                              {item.text}
                            </div>
                          )
                        }
                        return (
                          <div key={item.key} className={styles.messageBlock}>
                            {renderConversationBlock(item)}
                          </div>
                        )
                      })}
                      {message.showTyping ? (
                        <div className={`${styles.messageBody} ${styles.assistantTextItem}`}>
                          <TypingIndicator />
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
              onKeyDown={onComposerKeyDown}
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
          {composerHint ? <div className={styles.composerHint}>{composerHint}</div> : null}
        </div>
      ) : null}
    </div>
  )
}
