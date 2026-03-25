import { useMemo, useState } from 'react'
import type { SemanticBlock } from './semanticMapper'
import styles from './SemanticBlocks.module.css'

function clampLines(text: string, maxLines: number): { preview: string; clamped: boolean } {
  const lines = text.split('\n')
  if (lines.length <= maxLines) {
    return { preview: text, clamped: false }
  }
  return {
    preview: lines.slice(0, maxLines).join('\n'),
    clamped: true,
  }
}

function formatDuration(durationMs: number | null): string {
  if (durationMs === null) return '-'
  if (durationMs < 1000) return `${durationMs}ms`
  return `${(durationMs / 1000).toFixed(1)}s`
}

function formatStatus(status: 'running' | 'completed' | 'error'): string {
  if (status === 'running') return 'Running'
  if (status === 'completed') return 'Completed'
  return 'Error'
}

export function SemanticBlocks({ blocks }: { blocks: SemanticBlock[] }) {
  const [expandedSummary, setExpandedSummary] = useState(false)
  const [expandedTools, setExpandedTools] = useState<Record<string, boolean>>({})
  const summaryBlock = useMemo(
    () => blocks.find((block): block is Extract<SemanticBlock, { type: 'summary' }> => block.type === 'summary'),
    [blocks],
  )

  return (
    <div className={styles.root}>
      {summaryBlock ? (
        <section className={styles.summary}>
          <header className={styles.header}>
            <span className={styles.icon}>S</span>
            <span className={styles.title}>Summary</span>
          </header>
          {(() => {
            const { preview, clamped } = clampLines(summaryBlock.text, 5)
            const text = expandedSummary || !clamped ? summaryBlock.text : preview
            return (
              <>
                <pre className={styles.summaryText}>{text}</pre>
                {clamped ? (
                  <button
                    type="button"
                    className={styles.linkButton}
                    onClick={() => setExpandedSummary((v) => !v)}
                  >
                    {expandedSummary ? 'Show less' : 'Show more'}
                  </button>
                ) : null}
              </>
            )
          })()}
        </section>
      ) : null}

      {blocks
        .filter((block): block is Extract<SemanticBlock, { type: 'plan' }> => block.type === 'plan')
        .map((block, index) => (
          <section key={`plan-${index}`} className={styles.plan}>
            <header className={styles.header}>
              <span className={styles.icon}>P</span>
              <span className={styles.title}>Plan</span>
            </header>
            <ol className={styles.planList}>
              {block.steps.map((step) => (
                <li
                  key={step.id}
                  className={`${styles.planItem} ${step.status === 'active' ? styles.planItemActive : ''}`}
                >
                  <span className={styles.planMarker}>{step.status === 'completed' ? '\u2713' : '\u2022'}</span>
                  <span className={styles.planText}>{step.text}</span>
                </li>
              ))}
            </ol>
          </section>
        ))}

      {blocks
        .filter((block): block is Extract<SemanticBlock, { type: 'tool_action' }> => block.type === 'tool_action')
        .map((block) => {
          const expanded = Boolean(expandedTools[block.id])
          return (
            <section key={block.id} className={styles.tool}>
              <button
                type="button"
                className={styles.toolHeader}
                onClick={() => setExpandedTools((prev) => ({ ...prev, [block.id]: !expanded }))}
              >
                <span className={styles.icon}>T</span>
                <span className={styles.toolName}>{block.name}</span>
                <span className={styles.meta}>{formatStatus(block.status)}</span>
                <span className={styles.meta}>{formatDuration(block.durationMs)}</span>
                <span className={styles.chevron}>{expanded ? '\u25be' : '\u25b8'}</span>
              </button>
              {block.target ? <div className={styles.target}>{block.target}</div> : null}
              {expanded ? (
                <div className={styles.toolBody}>
                  {block.payload ? <pre className={styles.payload}>{JSON.stringify(block.payload, null, 2)}</pre> : null}
                  {block.output ? <pre className={styles.output}>{block.output}</pre> : null}
                  {typeof block.exitCode === 'number' ? (
                    <div className={styles.exitCode}>Exit code: {block.exitCode}</div>
                  ) : null}
                </div>
              ) : null}
            </section>
          )
        })}

      {blocks
        .filter((block): block is Extract<SemanticBlock, { type: 'error_blocker' }> => block.type === 'error_blocker')
        .map((block, index) => (
          <section key={`error-${index}`} className={styles.error}>
            <header className={styles.errorTitle}>{block.title}</header>
            <p className={styles.errorLine}><strong>Impact:</strong> {block.impact}</p>
            <p className={styles.errorLine}><strong>Attempted:</strong> {block.attempted}</p>
            {block.requiredDecision ? (
              <p className={styles.errorLine}><strong>Decision needed:</strong> {block.requiredDecision}</p>
            ) : null}
          </section>
        ))}
    </div>
  )
}
