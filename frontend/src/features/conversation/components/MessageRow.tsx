import type { ConversationMessageItem } from '../../../api/types'
import { ConversationMarkdown } from './ConversationMarkdown'
import styles from './ConversationFeed.module.css'

function roleLabel(role: ConversationMessageItem['role']) {
  if (role === 'user') return 'You'
  if (role === 'system') return 'System'
  return 'Assistant'
}

export function MessageRow({ item }: { item: ConversationMessageItem }) {
  const hasContent = item.text.trim().length > 0
  if (!hasContent) {
    return null
  }

  const rowClass =
    item.role === 'user'
      ? styles.rowMessageUser
      : item.role === 'system'
        ? styles.rowMessageSystem
        : styles.rowMessageAssistant
  const shellClass =
    item.role === 'user'
      ? styles.messageShellUser
      : item.role === 'system'
        ? styles.messageShellSystem
        : styles.messageShellAssistant
  const bubbleClass =
    item.role === 'user'
      ? styles.messageBubbleUser
      : item.role === 'system'
        ? styles.messageBubbleSystem
        : styles.messageBubbleAssistant

  return (
    <article className={`${styles.row} ${rowClass}`} data-testid={`conversation-item-${item.kind}`}>
      <div className={`${styles.messageShell} ${shellClass}`}>
        <div className={styles.roleLabel}>{roleLabel(item.role)}</div>
        <div className={`${styles.messageBubble} ${bubbleClass}`}>
          <ConversationMarkdown content={item.text} />
        </div>
      </div>
    </article>
  )
}
