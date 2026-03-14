import { useEffect, useMemo, useState } from 'react'
import type { AgentActivity, NodeDocuments, NodeRecord, NodeSpec } from '../../api/types'
import { AgentActivityCard } from './AgentActivityCard'
import { FieldRow, ListFieldRow, SectionCard } from './DocumentFormFields'
import { formatPhaseLabel, isDocumentReadOnly } from './DocumentPanelState'
import { LifecycleSummary } from './LifecycleSummary'
import styles from './DocumentPanel.module.css'

type Props = {
  node: NodeRecord
  documents: NodeDocuments | undefined
  isLoading: boolean
  isUpdating: boolean
  isGenerating: boolean
  isConfirming: boolean
  activity?: AgentActivity
  onReload: () => Promise<void>
  onSave: (payload: Partial<NodeSpec>) => Promise<void>
  onGenerate: () => Promise<void>
  onConfirm: () => Promise<void>
}

const EMPTY_SPEC: NodeSpec = {
  mission: {
    goal: '',
    success_outcome: '',
    implementation_level: '',
  },
  scope: {
    must_do: [],
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
    default_policy_when_unclear: '',
  },
  verification: {
    acceptance_checks: [],
    definition_of_done: '',
    evidence_expected: [],
  },
  execution_controls: {
    quality_profile: '',
    tooling_limits: [],
    output_expectation: '',
    conflict_policy: '',
    missing_decision_policy: '',
  },
  assumptions: {
    assumptions_in_force: [],
  },
}

function cloneSpec(spec: NodeSpec): NodeSpec {
  return JSON.parse(JSON.stringify(spec)) as NodeSpec
}

export function SpecPanel({
  node,
  documents,
  isLoading,
  isUpdating,
  isGenerating,
  isConfirming,
  activity,
  onReload,
  onSave,
  onGenerate,
  onConfirm,
}: Props) {
  const [form, setForm] = useState<NodeSpec>(EMPTY_SPEC)

  useEffect(() => {
    if (!documents) {
      return
    }
    setForm(cloneSpec(documents.spec))
  }, [documents, node.node_id])

  const isReadOnly = isDocumentReadOnly(node)
  const isDirty = useMemo(() => {
    if (!documents) {
      return false
    }
    return JSON.stringify(form) !== JSON.stringify(documents.spec)
  }, [documents, form])
  const generationStatus = documents?.state.spec_generation_status ?? 'idle'
  const plannerNeedsSpecReview =
    node.phase === 'blocked_on_spec_question' ||
    Boolean(documents?.state.spec_update_change_summary)
  const canConfirm =
    node.phase === 'spec_review' && !isReadOnly && !isDirty
  const canGenerate =
    !isReadOnly &&
    !isDirty &&
    (node.phase === 'spec_review' || node.phase === 'ready_for_execution') &&
    node.planning_thread_status !== 'active' &&
    !isGenerating &&
    generationStatus !== 'generating'
  const failure = documents?.state.last_agent_failure
  const specActivityCard =
    failure && (failure.operation === 'generate_spec' || failure.operation === 'brief_pipeline') ? (
      <AgentActivityCard
        status="Failed"
        tone="negative"
        message={failure.message || 'The agent could not refresh this spec.'}
      />
    ) : generationStatus === 'generating' ? (
      <AgentActivityCard
        status="Drafting Spec"
        message={activity?.message || 'The system is drafting the latest spec recommendation.'}
      />
    ) : activity?.status === 'operation_completed' &&
      (activity.operation === 'generate_spec' || activity.operation === 'brief_pipeline') ? (
      <AgentActivityCard
        status="Completed"
        tone="positive"
        message={activity.message || 'The latest spec draft is ready to review.'}
      />
    ) : null

  const updateScalar = <TSection extends keyof NodeSpec, TField extends keyof NodeSpec[TSection]>(
    section: TSection,
    field: TField,
    value: string,
  ) => {
    setForm((current) => ({
      ...current,
      [section]: {
        ...current[section],
        [field]: value,
      },
    }))
  }

  const updateList = <TSection extends keyof NodeSpec, TField extends keyof NodeSpec[TSection]>(
    section: TSection,
    field: TField,
    values: string[],
  ) => {
    setForm((current) => ({
      ...current,
      [section]: {
        ...current[section],
        [field]: values,
      },
    }))
  }

  if (!documents) {
    return (
      <div className={styles.panel}>
        <p className={styles.loading}>{isLoading ? 'Loading Spec...' : 'Spec is not loaded yet.'}</p>
        {!isLoading ? (
          <div className={styles.buttonRow}>
            <button type="button" className={styles.secondaryButton} onClick={() => void onReload()}>
              Load Spec
            </button>
          </div>
        ) : null}
      </div>
    )
  }

  return (
    <section className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h3 className={styles.title}>Spec</h3>
          <p className={styles.meta}>Phase: {formatPhaseLabel(node.phase)}</p>
        </div>
        <p className={styles.hint}>
          Editable execution contract. Agent initializes the draft; execution only follows confirmed Spec.
        </p>
      </div>

      <LifecycleSummary state={documents.state} />
      {specActivityCard}

      {plannerNeedsSpecReview ? (
        <div className={styles.actions}>
          <span className={styles.status}>
            Execution planning found a contract change. Review the Spec handoff in the Execution tab, update this Spec, then confirm it again before planning.
          </span>
        </div>
      ) : null}

      <div className={styles.sectionStack}>
        <SectionCard title="Mission">
          <FieldRow label="Goal">
            <input
              className={styles.input}
              aria-label="Goal"
              value={form.mission.goal}
              disabled={isReadOnly}
              onChange={(event) => updateScalar('mission', 'goal', event.target.value)}
            />
          </FieldRow>
          <FieldRow label="Success Outcome">
            <textarea
              className={styles.textarea}
              aria-label="Success Outcome"
              rows={4}
              value={form.mission.success_outcome}
              disabled={isReadOnly}
              onChange={(event) => updateScalar('mission', 'success_outcome', event.target.value)}
            />
          </FieldRow>
          <FieldRow label="Implementation Level">
            <input
              className={styles.input}
              aria-label="Implementation Level"
              value={form.mission.implementation_level}
              disabled={isReadOnly}
              onChange={(event) => updateScalar('mission', 'implementation_level', event.target.value)}
            />
          </FieldRow>
        </SectionCard>

        <SectionCard title="Scope">
          <ListFieldRow
            label="Must Do"
            values={form.scope.must_do}
            onChange={(values) => updateList('scope', 'must_do', values)}
          />
          <ListFieldRow
            label="Must Not Do"
            values={form.scope.must_not_do}
            onChange={(values) => updateList('scope', 'must_not_do', values)}
          />
          <ListFieldRow
            label="Deferred Work"
            values={form.scope.deferred_work}
            onChange={(values) => updateList('scope', 'deferred_work', values)}
          />
        </SectionCard>

        <SectionCard title="Constraints">
          <ListFieldRow
            label="Hard Constraints"
            values={form.constraints.hard_constraints}
            onChange={(values) => updateList('constraints', 'hard_constraints', values)}
          />
          <FieldRow label="Change Budget">
            <textarea
              className={styles.textarea}
              aria-label="Change Budget"
              rows={3}
              value={form.constraints.change_budget}
              disabled={isReadOnly}
              onChange={(event) => updateScalar('constraints', 'change_budget', event.target.value)}
            />
          </FieldRow>
          <ListFieldRow
            label="Touch Boundaries"
            values={form.constraints.touch_boundaries}
            onChange={(values) => updateList('constraints', 'touch_boundaries', values)}
          />
          <ListFieldRow
            label="External Dependencies"
            values={form.constraints.external_dependencies}
            onChange={(values) => updateList('constraints', 'external_dependencies', values)}
          />
        </SectionCard>

        <SectionCard title="Autonomy">
          <ListFieldRow
            label="Allowed Decisions"
            values={form.autonomy.allowed_decisions}
            onChange={(values) => updateList('autonomy', 'allowed_decisions', values)}
          />
          <ListFieldRow
            label="Requires Confirmation"
            values={form.autonomy.requires_confirmation}
            onChange={(values) => updateList('autonomy', 'requires_confirmation', values)}
          />
          <FieldRow label="Default Policy When Unclear">
            <input
              className={styles.input}
              aria-label="Default Policy When Unclear"
              value={form.autonomy.default_policy_when_unclear}
              disabled={isReadOnly}
              onChange={(event) =>
                updateScalar('autonomy', 'default_policy_when_unclear', event.target.value)
              }
            />
          </FieldRow>
        </SectionCard>

        <SectionCard title="Verification">
          <ListFieldRow
            label="Acceptance Checks"
            values={form.verification.acceptance_checks}
            onChange={(values) => updateList('verification', 'acceptance_checks', values)}
          />
          <FieldRow label="Definition Of Done">
            <textarea
              className={styles.textarea}
              aria-label="Definition Of Done"
              rows={3}
              value={form.verification.definition_of_done}
              disabled={isReadOnly}
              onChange={(event) =>
                updateScalar('verification', 'definition_of_done', event.target.value)
              }
            />
          </FieldRow>
          <ListFieldRow
            label="Evidence Expected"
            values={form.verification.evidence_expected}
            onChange={(values) => updateList('verification', 'evidence_expected', values)}
          />
        </SectionCard>

        <SectionCard title="Execution Controls">
          <FieldRow label="Quality Profile">
            <input
              className={styles.input}
              aria-label="Quality Profile"
              value={form.execution_controls.quality_profile}
              disabled={isReadOnly}
              onChange={(event) =>
                updateScalar('execution_controls', 'quality_profile', event.target.value)
              }
            />
          </FieldRow>
          <ListFieldRow
            label="Tooling Limits"
            values={form.execution_controls.tooling_limits}
            onChange={(values) => updateList('execution_controls', 'tooling_limits', values)}
          />
          <FieldRow label="Output Expectation">
            <textarea
              className={styles.textarea}
              aria-label="Output Expectation"
              rows={3}
              value={form.execution_controls.output_expectation}
              disabled={isReadOnly}
              onChange={(event) =>
                updateScalar('execution_controls', 'output_expectation', event.target.value)
              }
            />
          </FieldRow>
          <FieldRow label="Conflict Policy">
            <input
              className={styles.input}
              aria-label="Conflict Policy"
              value={form.execution_controls.conflict_policy}
              disabled={isReadOnly}
              onChange={(event) =>
                updateScalar('execution_controls', 'conflict_policy', event.target.value)
              }
            />
          </FieldRow>
          <FieldRow label="Missing Decision Policy">
            <input
              className={styles.input}
              aria-label="Missing Decision Policy"
              value={form.execution_controls.missing_decision_policy}
              disabled={isReadOnly}
              onChange={(event) =>
                updateScalar('execution_controls', 'missing_decision_policy', event.target.value)
              }
            />
          </FieldRow>
        </SectionCard>

        <SectionCard title="Assumptions">
          <ListFieldRow
            label="Assumptions In Force"
            values={form.assumptions.assumptions_in_force}
            onChange={(values) => updateList('assumptions', 'assumptions_in_force', values)}
          />
        </SectionCard>
      </div>

      <div className={styles.actions}>
        <span className={styles.status}>
          {isReadOnly
            ? 'Spec is locked while the node is executing or already closed.'
            : isDirty
              ? 'Save changes before confirming or refreshing the agent draft.'
              : generationStatus === 'generating' || isGenerating
                ? 'Refreshing agent-recommended Spec draft...'
                : generationStatus === 'failed'
                  ? 'Last draft refresh failed. Review the current Spec or try again.'
                  : node.phase === 'ready_for_execution'
                    ? 'Refreshing the draft will step the node back into spec review and abandon the current plan.'
                    : 'Confirm the Spec before planning.'}
        </span>
        <div className={styles.buttonRow}>
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={isReadOnly || isUpdating || isGenerating || !isDirty}
            onClick={() => void onSave(form)}
          >
            {isUpdating ? 'Saving...' : 'Save Spec'}
          </button>
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={!canGenerate}
            onClick={() => void onGenerate()}
          >
            {isGenerating || generationStatus === 'generating' ? 'Refreshing...' : 'Refresh Agent Draft'}
          </button>
          <button
            type="button"
            className={styles.primaryButton}
            disabled={!canConfirm || isConfirming || isGenerating || generationStatus === 'generating'}
            onClick={() => void onConfirm()}
          >
            {isConfirming ? 'Confirming...' : 'Confirm Spec'}
          </button>
        </div>
      </div>
    </section>
  )
}
