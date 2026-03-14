import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { BriefingPanel } from "../../src/features/breadcrumb/BriefingPanel";

const baseNode = {
  node_id: "node-1",
  parent_id: null,
  child_ids: [],
  title: "Restaurant website",
  description: "Ship the restaurant marketing site",
  status: "draft" as const,
  phase: "awaiting_brief" as const,
  node_kind: "root" as const,
  planning_mode: null,
  depth: 0,
  display_order: 0,
  hierarchical_number: "1",
  split_metadata: null,
  chat_session_id: null,
  has_planning_thread: false,
  has_execution_thread: false,
  planning_thread_status: null,
  execution_thread_status: null,
  has_ask_thread: false,
  ask_thread_status: null,
  is_superseded: false,
  created_at: "2026-03-12T00:00:00Z",
};

function makeDocuments() {
  return {
    task: {
      title: "Restaurant website",
      purpose: "Ship the restaurant marketing site",
      responsibility: "Own the public experience",
    },
    brief: {
      node_snapshot: {
        node_summary: "",
        why_this_node_exists_now: "",
        current_focus: "",
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
        status: "",
        completed_so_far: [],
        current_blockers: [],
        next_best_action: "",
      },
      pending_escalations: {
        open_risks: [],
        pending_user_decisions: [],
        fallback_direction_if_unanswered: "",
      },
    },
    briefing: {
      node_snapshot: {
        node_summary: "",
        why_this_node_exists_now: "",
        current_focus: "",
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
        status: "",
        completed_so_far: [],
        current_blockers: [],
        next_best_action: "",
      },
      pending_escalations: {
        open_risks: [],
        pending_user_decisions: [],
        fallback_direction_if_unanswered: "",
      },
    },
    spec: {
      mission: { goal: "", success_outcome: "", implementation_level: "" },
      scope: { must_do: [], must_not_do: [], deferred_work: [] },
      constraints: {
        hard_constraints: [],
        change_budget: "",
        touch_boundaries: [],
        external_dependencies: [],
      },
      autonomy: {
        allowed_decisions: [],
        requires_confirmation: [],
        default_policy_when_unclear: "",
      },
      verification: {
        acceptance_checks: [],
        definition_of_done: "",
        evidence_expected: [],
      },
      execution_controls: {
        quality_profile: "",
        tooling_limits: [],
        output_expectation: "",
        conflict_policy: "",
        missing_decision_policy: "",
      },
      assumptions: { assumptions_in_force: [] },
    },
    state: {
      phase: "awaiting_brief" as const,
      task_confirmed: true,
      briefing_confirmed: false,
      brief_generation_status: "failed" as const,
      brief_version: 0,
      brief_created_at: "",
      brief_created_from_predecessor_node_id: "",
      brief_generated_by: "",
      brief_source_hash: "",
      brief_source_refs: [],
      brief_late_upstream_policy: "ignore",
      spec_initialized: false,
      spec_generated: false,
      spec_generation_status: "idle" as const,
      spec_confirmed: false,
      active_spec_version: 0,
      spec_status: "draft" as const,
      spec_confirmed_at: "",
      initialized_from_brief_version: 0,
      spec_content_hash: "",
      active_plan_version: 0,
      plan_status: "none" as const,
      bound_plan_spec_version: 0,
      bound_plan_brief_version: 0,
      run_status: "idle" as const,
      pending_plan_questions: [],
      planning_thread_id: "",
      execution_thread_id: "",
      ask_thread_id: "",
      planning_thread_forked_from_node: "",
      planning_thread_bootstrapped_at: "",
      chat_session_id: "",
      last_agent_failure: {
        operation: "brief_pipeline" as const,
        message: "Brief generation failed.",
        occurred_at: "2026-03-12T00:00:00Z",
      },
    },
  };
}

describe("BriefingPanel", () => {
  it("offers a retry button when brief generation fails", () => {
    const onRetry = vi.fn(async () => undefined);

    render(
      <BriefingPanel
        node={baseNode}
        documents={makeDocuments()}
        isLoading={false}
        isRetrying={false}
        onReload={vi.fn(async () => undefined)}
        onRetry={onRetry}
      />,
    );

    expect(
      screen.getByText(
        "Last brief generation failed. Retry to continue to spec review.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Brief" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });
});
