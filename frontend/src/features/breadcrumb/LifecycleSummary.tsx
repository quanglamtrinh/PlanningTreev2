import type { NodeState, SpecGenerationStatus } from '../../api/types'
import { formatPhaseLabel } from './DocumentPanelState'
import styles from './DocumentPanel.module.css'

type Tone = 'positive' | 'neutral' | 'negative'

type Props = {
  state: NodeState
  compact?: boolean
}

function toneClassName(tone: Tone) {
  if (tone === 'positive') {
    return styles.summaryPositive
  }
  if (tone === 'negative') {
    return styles.summaryNegative
  }
  return styles.summaryNeutral
}

function boolLabel(value: boolean, positive = 'Ready', negative = 'Pending') {
  return {
    value: value ? positive : negative,
    tone: value ? ('positive' as const) : ('neutral' as const),
  }
}

function generationStatus(status: SpecGenerationStatus) {
  if (status === 'generating') {
    return { value: 'Generating', tone: 'neutral' as const }
  }
  if (status === 'failed') {
    return { value: 'Failed', tone: 'negative' as const }
  }
  return { value: 'Idle', tone: 'neutral' as const }
}

export function LifecycleSummary({ state, compact = false }: Props) {
  const items = [
    { label: 'Phase', value: formatPhaseLabel(state.phase), tone: 'neutral' as const },
    { label: 'Task', ...boolLabel(state.task_confirmed, 'Confirmed', 'Pending') },
    {
      label: 'Brief',
      value: state.brief_generation_status === 'ready' ? `v${state.brief_version || 1}` : state.brief_generation_status,
      tone:
        state.brief_generation_status === 'ready'
          ? ('positive' as const)
          : state.brief_generation_status === 'failed'
            ? ('negative' as const)
            : ('neutral' as const),
    },
    { label: 'Spec Draft', ...boolLabel(state.spec_initialized || state.spec_generated, 'Ready', 'Missing') },
    { label: 'Generation', ...generationStatus(state.spec_generation_status) },
    {
      label: 'Spec',
      value: state.spec_confirmed ? `Confirmed v${state.active_spec_version}` : state.spec_status,
      tone: state.spec_confirmed ? ('positive' as const) : ('neutral' as const),
    },
    {
      label: 'Plan',
      value: state.plan_status,
      tone:
        state.plan_status === 'ready' || state.plan_status === 'completed'
          ? ('positive' as const)
          : state.plan_status === 'abandoned'
            ? ('negative' as const)
            : ('neutral' as const),
    },
    {
      label: 'Run',
      value: state.run_status,
      tone:
        state.run_status === 'completed'
          ? ('positive' as const)
          : state.run_status === 'failed'
            ? ('negative' as const)
            : ('neutral' as const),
    },
  ]

  return (
    <div
      className={`${styles.summaryGrid} ${compact ? styles.summaryGridCompact : ''}`.trim()}
      data-testid="lifecycle-summary"
    >
      {items.map((item) => (
        <div key={item.label} className={styles.summaryItem}>
          <span className={styles.summaryLabel}>{item.label}</span>
          <span className={`${styles.summaryValue} ${toneClassName(item.tone)}`}>{item.value}</span>
        </div>
      ))}
    </div>
  )
}
