import { useEffect, useMemo, useState } from "react";
import type { AgentActivity, NodeDocuments, NodeRecord } from "../../api/types";
import { AgentActivityCard } from "./AgentActivityCard";
import { FieldRow, SectionCard } from "./DocumentFormFields";
import { formatPhaseLabel, isDocumentReadOnly } from "./DocumentPanelState";
import { LifecycleSummary } from "./LifecycleSummary";
import styles from "./DocumentPanel.module.css";

type Props = {
  node: NodeRecord;
  documents: NodeDocuments | undefined;
  isLoading: boolean;
  isUpdating: boolean;
  isConfirming: boolean;
  compact?: boolean;
  activity?: AgentActivity;
  onReload: () => Promise<void>;
  onSave: (payload: {
    title: string;
    purpose: string;
    responsibility: string;
  }) => Promise<void>;
  onConfirm: () => Promise<void>;
  onRetryBrief?: () => Promise<void>;
  onOpenBrief?: () => void;
  onOpenSpec?: () => void;
};

export function TaskPanel({
  node,
  documents,
  isLoading,
  isUpdating,
  isConfirming,
  compact = false,
  activity,
  onReload,
  onSave,
  onConfirm,
  onRetryBrief,
  onOpenBrief,
  onOpenSpec,
}: Props) {
  const [form, setForm] = useState({
    title: "",
    purpose: "",
    responsibility: "",
  });

  useEffect(() => {
    if (!documents) {
      return;
    }
    setForm(documents.task);
  }, [documents, node.node_id]);

  const isReadOnly = isDocumentReadOnly(node);
  const isDirty = useMemo(() => {
    if (!documents) {
      return false;
    }
    return (
      form.title !== documents.task.title ||
      form.purpose !== documents.task.purpose ||
      form.responsibility !== documents.task.responsibility
    );
  }, [documents, form]);
  const canConfirm =
    node.phase === "planning" &&
    !isReadOnly &&
    !isDirty &&
    form.title.trim().length > 0 &&
    form.purpose.trim().length > 0;
  const briefFailed = documents?.state.brief_generation_status === "failed";
  const canRetryBrief =
    briefFailed &&
    !isReadOnly &&
    !isDirty &&
    !isUpdating &&
    !isConfirming &&
    form.title.trim().length > 0 &&
    form.purpose.trim().length > 0 &&
    Boolean(onRetryBrief);
  const activityCard = useMemo(() => {
    if (!documents) {
      return null;
    }
    const failure = documents.state.last_agent_failure;
    const specReady =
      documents.state.spec_initialized || documents.state.spec_generated;

    if (
      failure &&
      (failure.operation === "brief_pipeline" ||
        failure.operation === "generate_spec")
    ) {
      return (
        <AgentActivityCard
          status="Failed"
          tone="negative"
          message={
            failure.message || "The agent could not finish preparing this node."
          }
        />
      );
    }

    if (documents.state.brief_generation_status === "generating") {
      return (
        <AgentActivityCard
          status="Generating Brief"
          message={
            activity?.message ||
            "The system is building the locked handoff brief."
          }
        />
      );
    }

    if (documents.state.spec_generation_status === "generating") {
      return (
        <AgentActivityCard
          status="Drafting Spec"
          message={
            activity?.message ||
            "The system is drafting the agent-recommended spec."
          }
          actionLabel={
            documents.state.brief_generation_status === "ready"
              ? "Open Brief"
              : undefined
          }
          onAction={
            documents.state.brief_generation_status === "ready"
              ? onOpenBrief
              : undefined
          }
        />
      );
    }

    if (
      activity?.status === "operation_completed" &&
      activity.operation === "brief_pipeline"
    ) {
      return (
        <AgentActivityCard
          status="Completed"
          tone="positive"
          message={
            activity.message || "The agent finished preparing this node."
          }
          actionLabel={
            specReady
              ? "Open Spec"
              : documents.state.brief_generation_status === "ready"
                ? "Open Brief"
                : undefined
          }
          onAction={
            specReady
              ? onOpenSpec
              : documents.state.brief_generation_status === "ready"
                ? onOpenBrief
                : undefined
          }
        />
      );
    }

    return null;
  }, [activity, documents, onOpenBrief, onOpenSpec]);

  if (!documents) {
    return (
      <div
        className={`${styles.panel} ${compact ? styles.panelCompact : ""}`.trim()}
      >
        <p className={styles.loading}>
          {isLoading ? "Loading task..." : "Task is not loaded yet."}
        </p>
        {!isLoading ? (
          <div className={styles.buttonRow}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => void onReload()}
            >
              Load Task
            </button>
          </div>
        ) : null}
      </div>
    );
  }

  return (
    <section
      className={`${styles.panel} ${compact ? styles.panelCompact : ""}`.trim()}
    >
      <div
        className={`${styles.header} ${compact ? styles.headerCompact : ""}`.trim()}
      >
        <div className={styles.titleBlock}>
          <h3 className={styles.title}>Task</h3>
          <p className={styles.meta}>Phase: {formatPhaseLabel(node.phase)}</p>
        </div>
        <p className={styles.hint}>
          Define the node statement of work before the system creates the locked
          Brief and agent draft Spec.
        </p>
      </div>

      <LifecycleSummary state={documents.state} compact={compact} />
      {activityCard}

      <div className={styles.sectionStack}>
        <SectionCard title="Task Definition">
          <FieldRow label="Title">
            <input
              className={styles.input}
              aria-label="Title"
              value={form.title}
              disabled={isReadOnly}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  title: event.target.value,
                }))
              }
            />
          </FieldRow>
          <FieldRow label="Purpose">
            <textarea
              className={styles.textarea}
              aria-label="Purpose"
              value={form.purpose}
              rows={4}
              disabled={isReadOnly}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  purpose: event.target.value,
                }))
              }
            />
          </FieldRow>
          <FieldRow label="Responsibility">
            <textarea
              className={styles.textarea}
              aria-label="Responsibility"
              value={form.responsibility}
              rows={4}
              disabled={isReadOnly}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  responsibility: event.target.value,
                }))
              }
            />
          </FieldRow>
        </SectionCard>
      </div>

      <div
        className={`${styles.actions} ${compact ? styles.actionsCompact : ""}`.trim()}
      >
        <span className={styles.status}>
          {isReadOnly
            ? "Task is locked while the node is executing or already closed."
            : briefFailed && isDirty
              ? "Save changes before retrying brief generation."
              : briefFailed
                ? "Brief generation failed. Retry to continue to spec review."
                : isDirty
                  ? "Save changes before confirming the task."
                  : node.phase === "planning"
                    ? "Confirm task to initialize the Brief and the agent-recommended Spec draft."
                    : "Editing a confirmed task will step the node back to planning."}
        </span>
        <div
          className={`${styles.buttonRow} ${compact ? styles.buttonRowCompact : ""}`.trim()}
        >
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={
              isReadOnly ||
              isUpdating ||
              !isDirty ||
              form.title.trim().length === 0
            }
            onClick={() => void onSave(form)}
          >
            {isUpdating ? "Saving..." : "Save Task"}
          </button>
          <button
            type="button"
            className={styles.primaryButton}
            disabled={
              briefFailed ? !canRetryBrief : !canConfirm || isConfirming
            }
            onClick={() => {
              if (briefFailed) {
                void onRetryBrief?.();
                return;
              }
              void onConfirm();
            }}
          >
            {isConfirming
              ? briefFailed
                ? "Retrying..."
                : "Confirming..."
              : briefFailed
                ? "Retry Brief"
                : "Confirm Task"}
          </button>
        </div>
      </div>
    </section>
  );
}
