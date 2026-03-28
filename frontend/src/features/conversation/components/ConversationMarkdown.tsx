import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import styles from './ConversationMarkdown.module.css'

export function ConversationMarkdown({ content }: { content: string }) {
  if (!content.trim()) {
    return null
  }

  return (
    <div className={styles.root}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}
