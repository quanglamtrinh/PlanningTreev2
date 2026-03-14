import type { AgentActivity, NodeDocuments, NodeRecord } from "../../api/types";
import { AgentActivityCard } from "./AgentActivityCard";
import { ReadOnlyFieldRow, SectionCard } from "./DocumentFormFields";
import { formatPhaseLabel, isDocumentReadOnly } from "./DocumentPanelState";
import { LifecycleSummary } from "./LifecycleSummary";
import styles from "./DocumentPanel.module.css";

type Props = {
  node: NodeRecord;
  documents: NodeDocuments | undefined;
  isLoading: boolean;
  isRetrying?: boolean;
  activity?: AgentActivity;
  onReload: () => Promise<void>;
  onRetry?: () => Promise<void>;
};

const BRIEF_SECTIONS = [
  {
    title: "Node Snapshot",
    rows: [
      {
        label: "Node Summary",
        key: ["node_snapshot", "node_summary"] as const,
      },
      {
        label: "Why This Node Exists Now",
        key: ["node_snapshot", "why_this_node_exists_now"] as const,
      },
      {
        label: "Current Focus",
        key: ["node_snapshot", "current_focus"] as const,
      },
    ],
  },
  {
    title: "Active Inherited Context",
    rows: [
      {
        label: "Active Goals From Parent",
        key: ["active_inherited_context", "active_goals_from_parent"] as const,
      },
      {
        label: "Active Constraints From Parent",
        key: [
          "active_inherited_context",
          "active_constraints_from_parent",
        ] as const,
      },
      {
        label: "Active Decisions In Force",
        key: ["active_inherited_context", "active_decisions_in_force"] as const,
      },
    ],
  },
  {
    title: "Accepted Upstream Facts",
    rows: [
      {
        label: "Accepted Outputs",
        key: ["accepted_upstream_facts", "accepted_outputs"] as const,
      },
      {
        label: "Available Artifacts",
        key: ["accepted_upstream_facts", "available_artifacts"] as const,
      },
      {
        label: "Confirmed Dependencies",
        key: ["accepted_upstream_facts", "confirmed_dependencies"] as const,
      },
    ],
  },
  {
    title: "Runtime State",
    rows: [
      { label: "Status", key: ["runtime_state", "status"] as const },
      {
        label: "Completed So Far",
        key: ["runtime_state", "completed_so_far"] as const,
      },
      {
        label: "Current Blockers",
        key: ["runtime_state", "current_blockers"] as const,
      },
      {
        label: "Next Best Action",
        key: ["runtime_state", "next_best_action"] as const,
      },
    ],
  },
  {
    title: "Pending Escalations",
    rows: [
      {
        label: "Open Risks",
        key: ["pending_escalations", "open_risks"] as const,
      },
      {
        label: "Pending User Decisions",
        key: ["pending_escalations", "pending_user_decisions"] as const,
      },
      {
        label: "Fallback Direction If Unanswered",
        key: [
          "pending_escalations",
          "fallback_direction_if_unanswered",
        ] as const,
      },
    ],
  },
];

export function BriefingPanel({
  node,
  documents,
  isLoading,
  isRetrying = false,
  activity,
  onReload,
  onRetry,
}: Props) {
  if (!documents) {
    return (
      <div className={styles.panel}>
        <p className={styles.loading}>
          {isLoading ? "Loading Brief..." : "Brief is not loaded yet."}
        </p>
        {!isLoading ? (
          <div className={styles.buttonRow}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => void onReload()}
            >
              Load Brief
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  const briefFailed = documents.state.brief_generation_status === "failed";
  const canRetry =
    briefFailed && !isDocumentReadOnly(node) && !isRetrying && Boolean(onRetry);

  return (
    <section className={styles.panel}>
      <div className={styles.header}>
        <div className={styles.titleBlock}>
          <h3 className={styles.title}>Brief</h3>
          <p className={styles.meta}>Phase: {formatPhaseLabel(node.phase)}</p>
        </div>
        <p className={styles.hint}>
          Locked handoff snapshot for this node. It preserves workflow context
          and never overrides Spec.
        </p>
      </div>

      <LifecycleSummary state={documents.state} />
      {documents.state.last_agent_failure &&
      (documents.state.last_agent_failure.operation === "brief_pipeline" ||
        documents.state.last_agent_failure.operation === "generate_spec") ? (
        <AgentActivityCard
          status="Failed"
          tone="negative"
          message={
            documents.state.last_agent_failure.message ||
            "The agent could not finish preparing this node."
          }
        />
      ) : documents.state.brief_generation_status === "generating" ? (
        <AgentActivityCard
          status="Generating Brief"
          message={
            activity?.message ||
            "The system is building the locked handoff brief."
          }
        />
      ) : documents.state.spec_generation_status === "generating" ? (
        <AgentActivityCard
          status="Drafting Spec"
          message={
            activity?.message ||
            "The system is drafting the agent-recommended spec."
          }
        />
      ) : activity?.status === "operation_completed" &&
        activity.operation === "brief_pipeline" ? (
        <AgentActivityCard
          status="Completed"
          tone="positive"
          message={
            activity.message ||
            "The brief and spec handoff are ready to review."
          }
        />
      ) : null}

      <div className={styles.sectionStack}>
        {BRIEF_SECTIONS.map((section) => (
          <SectionCard key={section.title} title={section.title}>
            {section.rows.map((row) => (
              <ReadOnlyFieldRow
                key={row.label}
                label={row.label}
                value={readBriefValue(documents, row.key[0], row.key[1])}
              />
            ))}
          </SectionCard>
        ))}
      </div>

      <div className={styles.actions}>
        <span className={styles.status}>
          {briefFailed
            ? "Last brief generation failed. Retry to continue to spec review."
            : `Brief created ${documents.state.brief_created_at || "not yet"} by ${
                documents.state.brief_generated_by || "system"
              }. This is a locked handoff snapshot; late upstream changes are intentionally ignored.`}
        </span>
        {briefFailed ? (
          <div className={styles.buttonRow}>
            <button
              type="button"
              className={styles.primaryButton}
              disabled={!canRetry}
              onClick={() => void onRetry?.()}
            >
              {isRetrying ? "Retrying..." : "Retry Brief"}
            </button>
          </div>
        ) : null}
      </div>
    </section>
  );
}

function readBriefValue(
  documents: NodeDocuments,
  section:
    | "node_snapshot"
    | "active_inherited_context"
    | "accepted_upstream_facts"
    | "runtime_state"
    | "pending_escalations",
  field: string,
) {
  const sectionValue = documents.brief[section] as unknown as Record<
    string,
    string | string[]
  >;
  return sectionValue[field] ?? "";
}
