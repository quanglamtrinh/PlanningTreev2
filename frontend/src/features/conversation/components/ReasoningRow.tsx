import type { ReasoningItem } from '../../../api/types'
import { ConversationMarkdown } from './ConversationMarkdown'
import styles from './ConversationFeed.module.css'
import { getReasoningPresentationMeta, type ReasoningPresentationMeta } from './useConversationViewState'

export function ReasoningRow({
  item,
  presentationMeta,
  isExpanded = false,
  onToggle,
}: {
  item: ReasoningItem
  presentationMeta?: ReasoningPresentationMeta
  isExpanded?: boolean
  onToggle?: (itemId: string) => void
}) {
  const meta = presentationMeta ?? getReasoningPresentationMeta(item)
  if (!meta.hasBody) {
    return null
  }

  const canToggle = Boolean(meta.visibleDetail)
  const showDetail = Boolean(meta.visibleDetail) && isExpanded

  return (
    <article className={`${styles.row} ${styles.rowCard}`} data-testid="conversation-item-reasoning">
      <div className={styles.card}>
        <div className={styles.cardHeader}>
          <div>
            <div className={styles.cardEyebrow}>Reasoning</div>
          </div>
          <div className={styles.cardMeta}>
            <div className={`${styles.statusPill} ${styles.statusInProgress}`}>{item.status}</div>
            {canToggle ? (
              <button
                type="button"
                className={styles.inlineToggle}
                onClick={() => onToggle?.(item.id)}
              >
                {showDetail ? 'Hide details' : 'Show details'}
              </button>
            ) : null}
          </div>
        </div>
        {meta.visibleSummary ? <ConversationMarkdown content={meta.visibleSummary} /> : null}
        {showDetail ? (
          <div className={styles.section}>
            <div className={styles.sectionTitle}>Details</div>
            <ConversationMarkdown content={meta.visibleDetail ?? ''} />
          </div>
        ) : null}
      </div>
    </article>
  )
}
