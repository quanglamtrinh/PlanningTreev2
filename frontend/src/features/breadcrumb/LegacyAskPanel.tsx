import { useEffect, useMemo, useRef } from 'react'

import type { NodeRecord } from '../../api/types'
import { useAskStore } from '../../stores/ask-store'
import { useProjectStore } from '../../stores/project-store'
import askStyles from './AskPanel.module.css'
import baseStyles from './ChatPanel.module.css'
import { DeltaContextCard } from './DeltaContextCard'

type Props = {
  node: NodeRecord
  projectId: string
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

export function LegacyAskPanel({ node, projectId }: Props) {
  const snapshot = useProjectStore((state) => state.snapshot)
  const session = useAskStore((state) => state.session)
  const composerDraft = useAskStore((state) => state.composerDraft)
  const connectionStatus = useAskStore((state) => state.connectionStatus)
  const isLoadingSession = useAskStore((state) => state.isLoadingSession)
  const isSendingMessage = useAskStore((state) => state.isSendingMessage)
  const error = useAskStore((state) => state.error)
  const setComposerDraft = useAskStore((state) => state.setComposerDraft)
  const sendMessage = useAskStore((state) => state.sendMessage)
  const resetSession = useAskStore((state) => state.resetSession)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)

  const lastMessageKey = useMemo(() => {
    if (!session || session.messages.length === 0) {
      return ''
    }
    const lastMessage = session.messages[session.messages.length - 1]
    return `${lastMessage.message_id}:${lastMessage.updated_at}:${lastMessage.content.length}`
  }, [session])

  const hasActiveChildren = useMemo(() => {
    if (!snapshot) {
      return false
    }
    const nodeById = new Map(snapshot.tree_state.node_registry.map((item) => [item.node_id, item]))
    return node.child_ids.some((childId) => {
      const child = nodeById.get(childId)
      return Boolean(child && !child.is_superseded)
    })
  }, [node.child_ids, snapshot])

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
  }, [lastMessageKey, session?.active_turn_id, session?.delta_context_packets.length])

  const isReadOnly = node.status === 'done' || node.is_superseded
  const isBusy = Boolean(session?.active_turn_id || isSendingMessage)
  const canSend =
    connectionStatus === 'connected' &&
    composerDraft.trim().length > 0 &&
    !session?.active_turn_id &&
    !isSendingMessage &&
    !isReadOnly
  const canReset = Boolean(session) && !session?.active_turn_id && !isSendingMessage && !isReadOnly

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
    const confirmed = window.confirm('Reset this ask session and clear all messages?')
    if (!confirmed) {
      return
    }
    try {
      await resetSession(projectId, node.node_id)
    } catch {
      return
    }
  }

  const placeholder = isReadOnly
    ? 'This ask thread is read-only.'
    : connectionStatus === 'connected'
      ? `Ask about ${node.title}...`
      : 'Waiting for connection...'

  return (
    <div className={baseStyles.panel}>
      <div className={baseStyles.statusBar}>
        <span className={`${baseStyles.dot} ${baseStyles[connectionStatus]}`} aria-hidden="true" />
        <span className={baseStyles.statusLabel}>{connectionStatus}</span>
        <span className={baseStyles.nodeLabel}>
          {node.hierarchical_number} / {node.title}
        </span>
        <button
          type="button"
          className={baseStyles.resetBtn}
          disabled={!canReset}
          title="Reset ask session"
          onClick={() => void handleReset()}
        >
          <ResetIcon />
          <span>Reset</span>
        </button>
      </div>

      {error ? <div className={baseStyles.errorBanner}>{error}</div> : null}
      {isReadOnly ? (
        <div className={`${askStyles.noticeBanner} ${askStyles.noticeBannerMuted}`}>
          This node is no longer mutable. The ask thread is read-only.
        </div>
      ) : null}
      {hasActiveChildren ? (
        <div className={`${askStyles.noticeBanner} ${askStyles.noticeBannerWarning}`}>
          This node has been split. New packet suggestions on the parent are ignored, and manual packet creation is unavailable.
        </div>
      ) : null}

      <div className={baseStyles.thread}>
        {isLoadingSession ? (
          <div className={baseStyles.emptyState}>
            <div className={baseStyles.loadingDots}>
              <span />
              <span />
              <span />
            </div>
            <p>Loading ask session...</p>
          </div>
        ) : null}

        {!isLoadingSession && session?.messages.length === 0 ? (
          <div className={baseStyles.emptyState}>
            <div className={baseStyles.emptyIcon} aria-hidden="true">
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
            <p className={baseStyles.emptyTitle}>Ask a question about this node&apos;s plan</p>
            <p className={baseStyles.emptyHint}>
              Explore scope, risks, dependencies, and alternatives for <strong>{node.title}</strong>.
            </p>
          </div>
        ) : null}

        {session?.messages.map((message) => (
          <article
            key={message.message_id}
            className={`${baseStyles.message} ${
              message.role === 'assistant' ? baseStyles.assistantMessage : baseStyles.userMessage
            }`}
          >
            {message.role === 'assistant' ? (
              <div className={baseStyles.assistantAvatar} aria-hidden="true">
                AI
              </div>
            ) : null}

            <div className={baseStyles.messageInner}>
              <div className={baseStyles.messageBody}>
                {message.content ||
                  (isBusy ? (
                    <span className={baseStyles.typingIndicator}>
                      <span />
                      <span />
                      <span />
                    </span>
                  ) : (
                    ''
                  ))}
              </div>
              <div className={baseStyles.messageMeta}>
                {message.status === 'streaming' ? <span className={baseStyles.streamingBadge}>streaming</span> : null}
                {message.status === 'error' ? <span className={baseStyles.errorBadge}>error</span> : null}
                <span className={baseStyles.timestamp}>{formatTimestamp(message.updated_at)}</span>
              </div>
              {message.error ? <p className={baseStyles.messageError}>{message.error}</p> : null}
            </div>
          </article>
        ))}

        <div ref={endRef} />
      </div>

      {session && session.delta_context_packets.length > 0 ? (
        <div className={askStyles.packetsSection}>
          <h4 className={askStyles.packetsSectionTitle}>Delta Context Packets</h4>
          {session.delta_context_packets.map((packet) => (
            <DeltaContextCard
              key={packet.packet_id}
              packet={packet}
              projectId={projectId}
              nodeId={node.node_id}
              askActive={Boolean(session.active_turn_id)}
              planningActive={node.planning_thread_status === 'active'}
              nodeReadOnly={isReadOnly}
              nodeHasActiveChildren={hasActiveChildren}
            />
          ))}
        </div>
      ) : null}

      <div className={baseStyles.composerWrap}>
        <div className={`${baseStyles.composerBox} ${isBusy ? baseStyles.composerBusy : ''}`}>
          <textarea
            ref={composerRef}
            className={baseStyles.composer}
            rows={1}
            value={composerDraft}
            placeholder={placeholder}
            disabled={connectionStatus !== 'connected' || isReadOnly}
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
            className={`${baseStyles.sendBtn} ${canSend ? baseStyles.sendBtnActive : ''}`}
            disabled={!canSend && !isBusy}
            aria-label={isBusy ? 'Stop generation' : 'Send message'}
            onClick={() => void handleSend()}
          >
            {isBusy ? <StopIcon /> : <SendIcon />}
          </button>
        </div>
        <p className={baseStyles.hint}>
          <kbd>Enter</kbd> to send / <kbd>Shift+Enter</kbd> for new line
        </p>
      </div>
    </div>
  )
}
