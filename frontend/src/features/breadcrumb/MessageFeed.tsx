import { memo, useEffect, useRef } from 'react'
import type { ChatMessage, MessagePart } from '../../api/types'
import { AgentSpinner } from '../../components/AgentSpinner'
import styles from './BreadcrumbChatView.module.css'
import feedStyles from './MessageFeed.module.css'
import { SemanticBlocks } from './SemanticBlocks'
import { mapMessageToSemanticBlocks } from './semanticMapper'

function inlineFormat(text: string): React.ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={i} className={styles.inlineCode}>{part.slice(1, -1)}</code>
    }
    return part
  })
}

function parseFenceLine(line: string): string | null {
  const match = line.match(/^```([A-Za-z0-9_+-]+)?\s*$/)
  if (!match) {
    return null
  }
  return match[1] ?? ''
}

function renderContent(content: string) {
  const lines = content.split('\n')
  const elements: React.ReactNode[] = []
  let tableBuffer: string[] = []
  let codeBlockBuffer: string[] = []
  let codeBlockLanguage: string | null = null
  let key = 0

  function flushTable() {
    if (tableBuffer.length === 0) return
    const rows = tableBuffer.map((r) =>
      r.split('|').map((c) => c.trim()).filter(Boolean),
    )
    const header = rows[0]
    const body = rows.slice(2)
    elements.push(
      <div className={styles.tableWrap} key={key++}>
        <table className={styles.table}>
          <thead>
            <tr>{header.map((h, i) => <th key={i}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {body.map((row, ri) => (
              <tr key={ri}>{row.map((cell, ci) => <td key={ci}>{cell}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>,
    )
    tableBuffer = []
  }

  function flushCodeBlock() {
    if (codeBlockLanguage === null) return
    const language = codeBlockLanguage
    elements.push(
      <div className={styles.codeBlockWrap} key={key++}>
        {language ? <div className={styles.codeBlockLabel}>{language}</div> : null}
        <pre className={styles.codeBlock}>
          <code>{codeBlockBuffer.join('\n')}</code>
        </pre>
      </div>,
    )
    codeBlockBuffer = []
    codeBlockLanguage = null
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const fenceLanguage = parseFenceLine(line)

    if (fenceLanguage !== null) {
      flushTable()
      if (codeBlockLanguage === null) {
        codeBlockLanguage = fenceLanguage
      } else {
        flushCodeBlock()
      }
      continue
    }

    if (codeBlockLanguage !== null) {
      codeBlockBuffer.push(line)
      continue
    }

    if (line.startsWith('|')) {
      tableBuffer.push(line)
      continue
    } else {
      flushTable()
    }
    if (line === '---') {
      elements.push(<hr key={key++} className={styles.divider} />)
    } else if (line.startsWith('## ')) {
      elements.push(<h3 key={key++} className={styles.heading2}>{line.slice(3)}</h3>)
    } else if (line.startsWith('### ')) {
      elements.push(<h4 key={key++} className={styles.heading3}>{line.slice(4)}</h4>)
    } else if (line.startsWith('**') && line.endsWith('**') && !line.slice(2, -2).includes('**')) {
      elements.push(<p key={key++} className={styles.bold}>{line.slice(2, -2)}</p>)
    } else if (line.startsWith('- ') || line.match(/^\d+\. /)) {
      const text = line.replace(/^[-\d]+\.?\s/, '')
      elements.push(<li key={key++} className={styles.listItem}>{inlineFormat(text)}</li>)
    } else if (line === '') {
      elements.push(<div key={key++} className={styles.spacer} />)
    } else {
      elements.push(<p key={key++} className={styles.para}>{inlineFormat(line)}</p>)
    }
  }
  flushTable()
  flushCodeBlock()
  return elements
}

function AssistantAvatar() {
  return (
    <div className={styles.avatar} aria-label="Assistant">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M12 2a4 4 0 014 4v1h1a3 3 0 013 3v6a3 3 0 01-3 3H7a3 3 0 01-3-3V10a3 3 0 013-3h1V6a4 4 0 014-4z"
          fill="currentColor"
          opacity="0.15"
        />
        <circle cx="9" cy="13" r="1.5" fill="currentColor" />
        <circle cx="15" cy="13" r="1.5" fill="currentColor" />
        <path
          d="M9.5 17c.8.6 1.7.9 2.5.9s1.7-.3 2.5-.9"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <path
          d="M8 7V6a4 4 0 118 0v1"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
      </svg>
    </div>
  )
}

function renderAssistantBody(msg: ChatMessage) {
  const semanticBlocks = mapMessageToSemanticBlocks(msg)
  if (semanticBlocks.length > 0) {
    return <SemanticBlocks blocks={semanticBlocks} />
  }
  if (msg.content) {
    return <div className={styles.content}>{renderContent(msg.content)}</div>
  }
  return null
}

function partsEqual(a: MessagePart[] | undefined, b: MessagePart[] | undefined): boolean {
  if (a === b) return true
  if (!a || !b) return a === b
  if (a.length !== b.length) return false
  for (let i = 0; i < a.length; i++) {
    if (JSON.stringify(a[i]) !== JSON.stringify(b[i])) return false
  }
  return true
}

const MessageFeedRow = memo(
  function MessageFeedRow({ msg }: { msg: ChatMessage }) {
    if (msg.role === 'system') {
      return null
    }

    return (
      <div
        className={`${styles.row} ${msg.role === 'user' ? styles.rowUser : styles.rowAssistant}`}
      >
        {msg.role === 'assistant' && <AssistantAvatar />}
        <div className={styles.bubble}>
          {msg.role === 'assistant' && msg.status === 'pending' && !msg.parts?.length && (
            <div className={styles.thinking}>
              <AgentSpinner />
            </div>
          )}
          {msg.role === 'assistant' && msg.status === 'error' && msg.error && (
            <div style={{ color: 'var(--text-error, #dc2626)', fontSize: 13, marginBottom: 4 }}>
              Error: {msg.error}
            </div>
          )}
          {msg.role === 'assistant' ? renderAssistantBody(msg) : (
            msg.content && <div className={styles.content}>{renderContent(msg.content)}</div>
          )}
        </div>
      </div>
    )
  },
  (prev, next) =>
    prev.msg.message_id === next.msg.message_id &&
    prev.msg.role === next.msg.role &&
    prev.msg.status === next.msg.status &&
    prev.msg.content === next.msg.content &&
    prev.msg.error === next.msg.error &&
    partsEqual(prev.msg.parts, next.msg.parts),
)

interface MessageFeedProps {
  messages: ChatMessage[]
  prefix?: React.ReactNode
  isLoading?: boolean
}

export function MessageFeed({ messages, prefix, isLoading }: MessageFeedProps) {
  const endRef = useRef<HTMLDivElement>(null)
  const prevCountRef = useRef(0)

  const tail = messages.length > 0 ? messages[messages.length - 1] : undefined
  const tailPartsKey = tail?.parts?.length ? JSON.stringify(tail.parts) : ''

  useEffect(() => {
    const n = messages.length
    const isNewMessage = n > prevCountRef.current
    prevCountRef.current = n

    if (n === 0) {
      return
    }

    const behavior: ScrollBehavior = isNewMessage ? 'smooth' : 'auto'
    endRef.current?.scrollIntoView({ behavior, block: 'end' })
  }, [messages.length, tail?.message_id, tail?.content, tail?.status, tail?.error, tailPartsKey])

  const showEmpty = !isLoading && messages.length === 0 && !prefix

  return (
    <div className={feedStyles.feed}>
      {prefix}
      {isLoading && (
        <div className={feedStyles.loadingInFeed}>Loading…</div>
      )}
      {showEmpty && (
        <div className={feedStyles.emptyInFeed}>
          Send a message to start the conversation
        </div>
      )}
      {messages.map((msg) => (
        <MessageFeedRow key={msg.message_id} msg={msg} />
      ))}
      <div ref={endRef} />
    </div>
  )
}
