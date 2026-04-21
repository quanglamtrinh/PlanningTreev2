import { useMemo } from 'react'
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import type { Components } from 'react-markdown'
import rehypeHighlight from 'rehype-highlight'
import remarkGfm from 'remark-gfm'
import { isLocalPathLikeLink, renderLocalLinkTarget } from './localLink'
import styles from './SharedMarkdownRenderer.module.css'

type MarkdownVariant = 'document' | 'context-shell'

type Props = {
  content: string
  projectRootPath?: string
  variant: MarkdownVariant
}

function transformMarkdownUrl(url: string, key: string): string {
  if (key === 'href' && isLocalPathLikeLink(url)) {
    return url
  }
  return defaultUrlTransform(url)
}

export function SharedMarkdownRenderer({
  content,
  projectRootPath,
  variant,
}: Props) {
  const components = useMemo<Components>(
    () => ({
      a: ({ node: _node, href, children, ...props }) => {
        const safeHref = typeof href === 'string' ? href : ''
        const localTarget = safeHref
          ? renderLocalLinkTarget(safeHref, { projectRootPath })
          : null
        if (localTarget) {
          return <code className={styles.localPath}>{localTarget}</code>
        }
        return (
          <a {...props} href={safeHref}>
            {children}
          </a>
        )
      },
      p: ({ children }) => <p className={styles.paragraph}>{children}</p>,
      ul: ({ children }) => <ul className={styles.unorderedList}>{children}</ul>,
      ol: ({ children }) => <ol className={styles.orderedList}>{children}</ol>,
      li: ({ children }) => <li className={styles.listItem}>{children}</li>,
      blockquote: ({ children }) => <blockquote className={styles.blockquote}>{children}</blockquote>,
      pre: ({ children }) => <pre className={styles.preBlock}>{children}</pre>,
      code: ({ className, children, ...props }) => {
        if (className?.startsWith('language-')) {
          return (
            <code {...props} className={`${styles.codeBlock} ${className}`}>
              {children}
            </code>
          )
        }
        return (
          <code {...props} className={styles.inlineCode}>
            {children}
          </code>
        )
      },
      table: ({ children }) => <table className={styles.table}>{children}</table>,
      th: ({ children }) => <th className={styles.tableHead}>{children}</th>,
      td: ({ children }) => <td className={styles.tableCell}>{children}</td>,
    }),
    [projectRootPath],
  )

  if (!content.trim()) {
    return null
  }

  const rootClassName =
    variant === 'document'
      ? `${styles.root} ${styles.document}`
      : `${styles.root} ${styles.contextShell}`

  return (
    <div className={rootClassName}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        urlTransform={(url, key) => transformMarkdownUrl(url, key)}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
