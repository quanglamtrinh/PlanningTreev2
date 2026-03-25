import { useState } from 'react'
import { AgentSpinner, SPINNER_WORDS_THINKING } from '../../components/AgentSpinner'
import styles from './ToolCallBlock.module.css'

function formatToolName(name: string): string {
  return name.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())
}

interface ToolCallBlockProps {
  toolName: string
  arguments: Record<string, unknown>
  status: 'running' | 'completed' | 'error'
  output: string | null
  exitCode: number | null
}

function summarizeCommand(args: Record<string, unknown>): string | null {
  const command = args.command
  return typeof command === 'string' && command.trim() ? command : null
}

export function ToolCallBlock({ toolName, arguments: args, status, output, exitCode }: ToolCallBlockProps) {
  const [expanded, setExpanded] = useState(false)
  const commandSummary = summarizeCommand(args)

  return (
    <div className={styles.root}>
      <div className={styles.header} onClick={() => setExpanded(!expanded)}>
        <span className={styles.icon}>
          {status === 'running' ? (
            <AgentSpinner words={SPINNER_WORDS_THINKING} className={styles.runningSpinner} />
          ) : status === 'error' ? (
            '\u2717'
          ) : (
            '\u2713'
          )}
        </span>
        <span className={styles.name}>{formatToolName(toolName)}</span>
        <span className={styles.chevron}>{expanded ? '\u25be' : '\u25b8'}</span>
      </div>
      {commandSummary && <div className={styles.summary}>{commandSummary}</div>}
      {expanded && (
        <>
          <pre className={styles.args}>{JSON.stringify(args, null, 2)}</pre>
          {output && <pre className={styles.output}>{output}</pre>}
          {exitCode !== null && <div className={styles.exitCode}>Exit code: {exitCode}</div>}
        </>
      )}
    </div>
  )
}
