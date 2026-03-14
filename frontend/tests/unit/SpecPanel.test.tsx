import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { SpecPanel } from '../../src/features/breadcrumb/SpecPanel'

const baseNode = {
  node_id: 'node-1',
  parent_id: null,
  child_ids: [],
  title: 'Alpha',
  description: 'Ship phase 5',
  status: 'draft' as const,
  phase: 'spec_review' as const,
  node_kind: 'root' as const,
  planning_mode: null,
  depth: 0,
  display_order: 0,
  hierarchical_number: '1',
  split_metadata: null,
  chat_session_id: null,
  has_planning_thread: false,
  has_execution_thread: false,
  planning_thread_status: 'idle' as const,
  execution_thread_status: null,
  has_ask_thread: false,
  ask_thread_status: null,
  is_superseded: false,
  created_at: '2026-03-12T00:00:00Z',
}

function makeDocuments(
  overrides: Partial<{
    state: Partial<{
      spec_generated: boolean
      spec_generation_status: 'idle' | 'generating' | 'failed'
      spec_confirmed: boolean
    }>
  }> = {},
) {
  return {
    task: {
      title: 'Alpha',
      purpose: 'Ship phase 5',
      responsibility: 'Own the release',
    },
    brief: {
      node_snapshot: {
        node_summary: 'Alpha',
        why_this_node_exists_now: 'Ship phase 5',
        current_focus: 'Own the release',
      },
      active_inherited_context: {
        active_goals_from_parent: [],
        active_constraints_from_parent: [],
        active_decisions_in_force: [],
      },
      accepted_upstream_facts: {
        accepted_outputs: [],
        available_artifacts: [],
        confirmed_dependencies: [],
      },
      runtime_state: {
        status: 'ready',
        completed_so_far: [],
        current_blockers: [],
        next_best_action: 'Draft spec',
      },
      pending_escalations: {
        open_risks: [],
        pending_user_decisions: [],
        fallback_direction_if_unanswered: '',
      },
    },
    briefing: {
      node_snapshot: {
        node_summary: 'Alpha',
        why_this_node_exists_now: 'Ship phase 5',
        current_focus: 'Own the release',
      },
      active_inherited_context: {
        active_goals_from_parent: [],
        active_constraints_from_parent: [],
        active_decisions_in_force: [],
      },
      accepted_upstream_facts: {
        accepted_outputs: [],
        available_artifacts: [],
        confirmed_dependencies: [],
      },
      runtime_state: {
        status: 'ready',
        completed_so_far: [],
        current_blockers: [],
        next_best_action: 'Draft spec',
      },
      pending_escalations: {
        open_risks: [],
        pending_user_decisions: [],
        fallback_direction_if_unanswered: '',
      },
    },
    spec: {
      mission: {
        goal: 'Ship phase 5',
        success_outcome: 'Release shipped',
        implementation_level: 'working',
      },
      scope: {
        must_do: ['Own the release'],
        must_not_do: [],
        deferred_work: [],
      },
      constraints: {
        hard_constraints: [],
        change_budget: '',
        touch_boundaries: [],
        external_dependencies: [],
      },
      autonomy: {
        allowed_decisions: [],
        requires_confirmation: [],
        default_policy_when_unclear: 'ask_user',
      },
      verification: {
        acceptance_checks: ['Release notes updated'],
        definition_of_done: '',
        evidence_expected: [],
      },
      execution_controls: {
        quality_profile: 'standard',
        tooling_limits: [],
        output_expectation: '',
        conflict_policy: 'reopen_spec',
        missing_decision_policy: 'reopen_spec',
      },
      assumptions: {
        assumptions_in_force: [],
      },
    },
    state: {
      phase: 'spec_review' as const,
      task_confirmed: true,
      briefing_confirmed: true,
      brief_generation_status: 'ready' as const,
      brief_version: 1,
      brief_created_at: '',
      brief_created_from_predecessor_node_id: '',
      brief_generated_by: 'agent',
      brief_source_hash: '',
      brief_source_refs: [],
      brief_late_upstream_policy: 'ignore',
      spec_initialized: true,
      spec_generated: false,
      spec_generation_status: 'idle' as const,
      spec_confirmed: false,
      active_spec_version: 0,
      spec_status: 'draft' as const,
      spec_confirmed_at: '',
      initialized_from_brief_version: 1,
      spec_content_hash: '',
      active_plan_version: 0,
      plan_status: 'none' as const,
      bound_plan_spec_version: 0,
      bound_plan_brief_version: 0,
      run_status: 'idle' as const,
      pending_plan_questions: [],
      pending_spec_questions: [],
      planning_thread_id: '',
      execution_thread_id: '',
      ask_thread_id: '',
      planning_thread_forked_from_node: '',
      planning_thread_bootstrapped_at: '',
      chat_session_id: '',
      ...(overrides.state ?? {}),
    },
  }
}

describe('SpecPanel', () => {
  it('renders the structured form and triggers agent draft refresh', () => {
    const onGenerate = vi.fn(async () => undefined)

    render(
      <SpecPanel
        node={baseNode}
        documents={makeDocuments()}
        isLoading={false}
        isUpdating={false}
        isGenerating={false}
        isConfirming={false}
        onReload={vi.fn(async () => undefined)}
        onSave={vi.fn(async () => undefined)}
        onGenerate={onGenerate}
        onConfirm={vi.fn(async () => undefined)}
      />,
    )

    expect(screen.getByTestId('lifecycle-summary')).toBeInTheDocument()
    expect(screen.getByLabelText('Goal')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Refresh Agent Draft' }))
    expect(onGenerate).toHaveBeenCalledTimes(1)
  })

  it('shows failed generation messaging', () => {
    render(
      <SpecPanel
        node={baseNode}
        documents={makeDocuments({
          state: {
            spec_generated: true,
            spec_generation_status: 'failed',
          },
        })}
        isLoading={false}
        isUpdating={false}
        isGenerating={false}
        isConfirming={false}
        onReload={vi.fn(async () => undefined)}
        onSave={vi.fn(async () => undefined)}
        onGenerate={vi.fn(async () => undefined)}
        onConfirm={vi.fn(async () => undefined)}
      />,
    )

    expect(screen.getByRole('button', { name: 'Refresh Agent Draft' })).toBeInTheDocument()
    expect(screen.getByText('Last draft refresh failed. Review the current Spec or try again.')).toBeInTheDocument()
  })

  it('disables confirm while the local spec form is dirty or generation is active', () => {
    const props = {
      node: baseNode,
      documents: makeDocuments({
        state: {
          spec_generated: true,
        },
      }),
      isLoading: false,
      isUpdating: false,
      isConfirming: false,
      onReload: vi.fn(async () => undefined),
      onSave: vi.fn(async () => undefined),
      onGenerate: vi.fn(async () => undefined),
      onConfirm: vi.fn(async () => undefined),
    }

    const { rerender } = render(<SpecPanel {...props} isGenerating={true} />)

    expect(screen.getByRole('button', { name: 'Refreshing...' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Confirm Spec' })).toBeDisabled()

    rerender(<SpecPanel {...props} isGenerating={false} />)
    fireEvent.change(screen.getByLabelText('Goal'), { target: { value: 'Changed goal' } })

    expect(screen.getByRole('button', { name: 'Save Spec' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Confirm Spec' })).toBeDisabled()
  })
})
