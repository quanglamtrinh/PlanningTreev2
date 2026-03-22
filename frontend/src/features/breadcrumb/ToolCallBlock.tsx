import { useState } from 'react'
import styles from './ToolCallBlock.module.css'

function formatToolName(name: string): string {
  return name.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

interface ToolCallBlockProps {
  toolName: string
  arguments: Record<string, unknown>
  status: 'running' | 'completed' | 'error'
}

export function ToolCallBlock({ toolName, arguments: args, status }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className={styles.root}>
      <div className={styles.header} onClick={() => setExpanded(!expanded)}>
        <span className={styles.icon}>
          {status === 'running' ? (
            <span className={styles.spinner} />
          ) : status === 'error' ? (
            '\u2717'
          ) : (
            '\u2713'
          )}
        </span>
        <span className={styles.name}>{formatToolName(toolName)}</span>
        <span className={styles.chevron}>{expanded ? '\u25be' : '\u25b8'}</span>
      </div>
      {expanded && (
        <pre className={styles.args}>{JSON.stringify(args, null, 2)}</pre>
      )}
    </div>
  )
}
