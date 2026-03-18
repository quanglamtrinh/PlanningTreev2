import type { SplitMode } from '../../api/types'

export type GraphSplitOption = {
  id: SplitMode
  label: string
  description: string
}

export const GRAPH_SPLIT_OPTIONS: readonly GraphSplitOption[] = [
  {
    id: 'workflow',
    label: 'Workflow',
    description: 'Workflow-first sequential breakdown from setup through completion.',
  },
  {
    id: 'simplify_workflow',
    label: 'Simplify Workflow',
    description: 'Smallest valid core workflow first, then add back the next essential steps.',
  },
  {
    id: 'phase_breakdown',
    label: 'Phase Breakdown',
    description: 'Phase-based delivery starting with the lowest-blast-radius step.',
  },
  {
    id: 'agent_breakdown',
    label: 'Agent Breakdown',
    description: 'Conservative boundary split by dependency, risk, migration, and cleanup.',
  },
]
