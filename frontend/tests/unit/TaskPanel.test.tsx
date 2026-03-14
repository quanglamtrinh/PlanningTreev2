import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TaskPanel } from "../../src/features/breadcrumb/TaskPanel";

const baseNode = {
  node_id: "node-1",
  parent_id: null,
  child_ids: [],
  title: "Alpha",
  description: "Ship phase 5",
  status: "draft" as const,
  phase: "planning" as const,
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
      title: "Alpha",
      purpose: "Ship phase 5",
      responsibility: "Own the release",
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
      phase: "planning" as const,
      task_confirmed: false,
      briefing_confirmed: false,
      brief_generation_status: "missing" as const,
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
      pending_spec_questions: [],
      planning_thread_id: "",
      execution_thread_id: "",
      ask_thread_id: "",
      planning_thread_forked_from_node: "",
      planning_thread_bootstrapped_at: "",
      chat_session_id: "",
    },
  };
}

function makeFailedBriefDocuments() {
  const documents = makeDocuments();
  return {
    ...documents,
    state: {
      ...documents.state,
      phase: "awaiting_brief" as const,
      task_confirmed: true,
      brief_generation_status: "failed" as const,
      last_agent_failure: {
        operation: "brief_pipeline" as const,
        message: "Brief generation failed.",
        occurred_at: "2026-03-12T00:00:00Z",
      },
    },
  };
}

describe("TaskPanel", () => {
  it("renders lifecycle summary and saves explicit task edits", () => {
    const onSave = vi.fn(async () => undefined);

    render(
      <TaskPanel
        node={baseNode}
        documents={makeDocuments()}
        isLoading={false}
        isUpdating={false}
        isConfirming={false}
        onReload={vi.fn(async () => undefined)}
        onSave={onSave}
        onConfirm={vi.fn(async () => undefined)}
      />,
    );

    expect(screen.getByTestId("lifecycle-summary")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Purpose"), {
      target: { value: "Clarified purpose" },
    });
    expect(screen.getByRole("button", { name: "Confirm Task" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Save Task" }));

    expect(onSave).toHaveBeenCalledWith({
      title: "Alpha",
      purpose: "Clarified purpose",
      responsibility: "Own the release",
    });
  });

  it("confirms the task when the saved document is ready", () => {
    const onConfirm = vi.fn(async () => undefined);

    render(
      <TaskPanel
        node={baseNode}
        documents={makeDocuments()}
        isLoading={false}
        isUpdating={false}
        isConfirming={false}
        onReload={vi.fn(async () => undefined)}
        onSave={vi.fn(async () => undefined)}
        onConfirm={onConfirm}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Confirm Task" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("supports compact read-only rendering for executing nodes", () => {
    render(
      <TaskPanel
        node={{
          ...baseNode,
          phase: "executing" as const,
          status: "in_progress" as const,
        }}
        documents={makeDocuments()}
        isLoading={false}
        isUpdating={false}
        isConfirming={false}
        compact
        onReload={vi.fn(async () => undefined)}
        onSave={vi.fn(async () => undefined)}
        onConfirm={vi.fn(async () => undefined)}
      />,
    );

    expect(
      screen.getByText(
        "Task is locked while the node is executing or already closed.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save Task" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Confirm Task" })).toBeDisabled();
  });

  it("offers a retry action when brief generation fails", () => {
    const onRetryBrief = vi.fn(async () => undefined);

    render(
      <TaskPanel
        node={{ ...baseNode, phase: "awaiting_brief" as const }}
        documents={makeFailedBriefDocuments()}
        isLoading={false}
        isUpdating={false}
        isConfirming={false}
        onReload={vi.fn(async () => undefined)}
        onSave={vi.fn(async () => undefined)}
        onConfirm={vi.fn(async () => undefined)}
        onRetryBrief={onRetryBrief}
      />,
    );

    expect(
      screen.getByText(
        "Brief generation failed. Retry to continue to spec review.",
      ),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry Brief" }));
    expect(onRetryBrief).toHaveBeenCalledTimes(1);
  });
});
