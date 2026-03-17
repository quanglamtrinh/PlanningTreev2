import { useEffect, useMemo, useState, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'

import styles from './ConversationMarkdown.module.css'

type Props = {
  value: string
  className?: string
}

type CodeBlockProps = {
  language: string | null
  value: string
}

function extractLanguage(className?: string) {
  if (!className) {
    return null
  }
  const match = className.match(/language-([\w-]+)/i)
  return match ? match[1] : null
}

function CodeBlock({ language, value }: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const trimmedValue = useMemo(() => value.replace(/\n$/, ''), [value])

  useEffect(() => {
    if (!copied) {
      return undefined
    }
    const timer = window.setTimeout(() => {
      setCopied(false)
    }, 1200)
    return () => window.clearTimeout(timer)
  }, [copied])

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(trimmedValue)
      setCopied(true)
    } catch {
      return
    }
  }

  return (
    <div className={styles.codeFrame}>
      <div className={styles.codeHeader}>
        <span className={styles.codeLanguage}>{language ?? 'text'}</span>
        <button
          type="button"
          className={`${styles.codeCopyButton}${copied ? ` ${styles.isCopied}` : ''}`}
          onClick={() => void handleCopy()}
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
      <pre className={styles.codePre}>
        <code>{trimmedValue}</code>
      </pre>
    </div>
  )
}

function readText(children: ReactNode): string {
  if (typeof children === 'string') {
    return children
  }
  if (Array.isArray(children)) {
    return children.map((child) => readText(child)).join('')
  }
  if (children && typeof children === 'object' && 'props' in children) {
    const props = children.props as { children?: ReactNode }
    return readText(props.children ?? '')
  }
  return ''
}

export function ConversationMarkdown({ value, className }: Props) {
  const components = useMemo<Components>(
    () => ({
      pre({ children }) {
        const codeChild = Array.isArray(children) ? children[0] : children
        if (!codeChild || typeof codeChild !== 'object' || !('props' in codeChild)) {
          return <pre className={styles.codeBlock}>{children}</pre>
        }
        const props = codeChild.props as {
          className?: string
          children?: ReactNode
        }
        return (
          <CodeBlock
            language={extractLanguage(props.className)}
            value={readText(props.children ?? '')}
          />
        )
      },
      code({ className: codeClassName, children }) {
        if (codeClassName) {
          return <code className={codeClassName}>{children}</code>
        }
        return <code className={styles.inlineCode}>{children}</code>
      },
    }),
    [],
  )

  return (
    <div className={[styles.markdown, className].filter(Boolean).join(' ')}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {value}
      </ReactMarkdown>
    </div>
  )
}
