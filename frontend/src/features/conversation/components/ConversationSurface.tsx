import type { ConversationRenderMessage } from '../model/buildConversationRenderModel'
import { renderConversationBlock } from './ConversationBlocks'
import { ExecutionConversationSurface } from './ExecutionConversationSurface'
import type {
  ConversationSurfaceMessageAction,
  ConversationSurfaceProps,
} from './ConversationSurface.types'
import styles from './ConversationSurface.module.css'

export type { ConversationSurfaceConnectionState } from './ConversationSurface.types'

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

function renderConversationMessage(
  message: ConversationRenderMessage,
  actions: ConversationSurfaceMessageAction[] = [],
) {
  return (
    <article key={message.messageId} className={`${styles.message} ${styles[message.roleTone]}`}>
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
        {actions.length > 0 ? (
          <div className={styles.messageActions}>
            {actions.map((action) => (
              <button
                key={action.key}
                type="button"
                className={styles.messageActionButton}
                disabled={action.disabled}
                onClick={() => action.onPress()}
              >
                {action.label}
              </button>
            ))}
          </div>
        ) : null}
        {message.errorText ? <p className={styles.messageError}>{message.errorText}</p> : null}
      </div>
    </article>
  )
}

function MinimalConversationSurface({
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
  messageActions = {},
  streamAction = null,
}: ConversationSurfaceProps) {
  const entries = model?.entries ?? []
  const showTranscript = entries.length > 0
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
          {streamAction ? (
            <button
              type="button"
              className={styles.headerActionButton}
              disabled={streamAction.disabled}
              onClick={() => streamAction.onPress()}
            >
              {streamAction.label}
            </button>
          ) : null}
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
          ? entries.map((entry) => {
              if (entry.kind === 'message') {
                return renderConversationMessage(entry.message, messageActions[entry.message.messageId] ?? [])
              }
              return (
                <details key={entry.key} className={styles.replayGroup}>
                  <summary className={styles.replaySummary}>{entry.label}</summary>
                  <div className={styles.replayMessages}>
                    {entry.messages.map((message) =>
                      renderConversationMessage(message, messageActions[message.messageId] ?? []),
                    )}
                  </div>
                </details>
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

export function ConversationSurface(props: ConversationSurfaceProps) {
  if (props.variant === 'codex_execution') {
    return <ExecutionConversationSurface {...props} />
  }
  return <MinimalConversationSurface {...props} />
}
