import { AgentSpinner, SPINNER_WORDS_THINKING } from '../../components/AgentSpinner'
import styles from './PlanItemBlock.module.css'

interface PlanItemBlockProps {
  content: string
  isStreaming: boolean
}

export function PlanItemBlock({ content, isStreaming }: PlanItemBlockProps) {
  return (
    <div className={styles.root}>
      <span className={styles.icon}>
        {isStreaming ? (
          <AgentSpinner words={SPINNER_WORDS_THINKING} className={styles.spinner} />
        ) : (
          '\u2713'
        )}
      </span>
      <span className={styles.content}>{content}</span>
    </div>
  )
}
