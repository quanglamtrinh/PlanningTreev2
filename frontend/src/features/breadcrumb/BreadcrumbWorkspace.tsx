import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import {
  useAgentEventStream,
  useAskSessionStream,
  useChatSessionStream,
  usePlanningEventStream,
} from "../../api/hooks";
import { useChatStore } from "../../stores/chat-store";
import { useProjectStore } from "../../stores/project-store";
import { useUIStore } from "../../stores/ui-store";
import { AgentActivityCard } from "./AgentActivityCard";
import { AskPanel } from "./AskPanel";
import { BriefingPanel } from "./BriefingPanel";
import { BreadcrumbHeader } from "./BreadcrumbHeader";
import { ChatPanel } from "./ChatPanel";
import { MarkDoneButton } from "./MarkDoneButton";
import { PlanningPanel } from "./PlanningPanel";
import { SpecPanel } from "./SpecPanel";
import { TaskPanel } from "./TaskPanel";
import styles from "./BreadcrumbWorkspace.module.css";

type TabId = "planning" | "task" | "ask" | "briefing" | "spec" | "execution";
type RequestedTabId = TabId | "info";

const TABS: { id: TabId; label: string }[] = [
  { id: "planning", label: "Planning" },
  { id: "task", label: "Task" },
  { id: "ask", label: "Ask" },
  { id: "briefing", label: "Brief" },
  { id: "spec", label: "Spec" },
  { id: "execution", label: "Execution" },
];

function resolveRequestedTab(value: RequestedTabId | undefined): TabId {
  if (value === "info") {
    return "briefing";
  }
  if (
    value === "task" ||
    value === "ask" ||
    value === "briefing" ||
    value === "spec" ||
    value === "execution"
  ) {
    return value;
  }
  return "planning";
}

export function BreadcrumbWorkspace() {
  const { projectId, nodeId } = useParams<{
    projectId: string;
    nodeId: string;
  }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<TabId>(() => {
    const initialTab = (location.state as { activeTab?: RequestedTabId } | null)
      ?.activeTab;
    return resolveRequestedTab(initialTab);
  });
  const [isPlanningAction, setIsPlanningAction] = useState(false);
  const [isExecutingAction, setIsExecutingAction] = useState(false);
  const [planInputDrafts, setPlanInputDrafts] = useState<Record<string, string>>(
    {},
  );
  const [planInputError, setPlanInputError] = useState<string | null>(null);
  const [isResolvingPlanInput, setIsResolvingPlanInput] = useState(false);
  const initialize = useProjectStore((state) => state.initialize);
  const loadProject = useProjectStore((state) => state.loadProject);
  const selectNode = useProjectStore((state) => state.selectNode);
  const startPlan = useProjectStore((state) => state.startPlan);
  const executeNode = useProjectStore((state) => state.executeNode);
  const loadNodeDocuments = useProjectStore((state) => state.loadNodeDocuments);
  const updateNodeTask = useProjectStore((state) => state.updateNodeTask);
  const updateNodeSpec = useProjectStore((state) => state.updateNodeSpec);
  const confirmTask = useProjectStore((state) => state.confirmTask);
  const confirmSpec = useProjectStore((state) => state.confirmSpec);
  const generateNodeSpec = useProjectStore((state) => state.generateNodeSpec);
  const patchNodeStatus = useProjectStore((state) => state.patchNodeStatus);
  const hasInitialized = useProjectStore((state) => state.hasInitialized);
  const isInitializing = useProjectStore((state) => state.isInitializing);
  const isLoadingSnapshot = useProjectStore((state) => state.isLoadingSnapshot);
  const snapshot = useProjectStore((state) => state.snapshot);
  const activeProjectId = useProjectStore((state) => state.activeProjectId);
  const selectedNodeId = useProjectStore((state) => state.selectedNodeId);
  const documentsByNode = useProjectStore((state) => state.documentsByNode);
  const agentActivityByNode = useProjectStore(
    (state) => state.agentActivityByNode,
  );
  const isLoadingDocuments = useProjectStore(
    (state) => state.isLoadingDocuments,
  );
  const isUpdatingDocument = useProjectStore(
    (state) => state.isUpdatingDocument,
  );
  const isGeneratingSpec = useProjectStore((state) => state.isGeneratingSpec);
  const isConfirmingNode = useProjectStore((state) => state.isConfirmingNode);
  const bootstrap = useProjectStore((state) => state.bootstrap);
  const chatSession = useChatStore((state) => state.session);
  const setComposerDraft = useChatStore((state) => state.setComposerDraft);
  const setActiveSurface = useUIStore((state) => state.setActiveSurface);

  useEffect(() => {
    setActiveSurface("breadcrumb");
    void initialize();
  }, [initialize, setActiveSurface]);

  useEffect(() => {
    if (!hasInitialized || !projectId) {
      return;
    }
    if (!bootstrap?.workspace_configured) {
      navigate("/", { replace: true });
      return;
    }
    if (activeProjectId !== projectId) {
      void loadProject(projectId).catch(() => navigate("/", { replace: true }));
    }
  }, [
    activeProjectId,
    bootstrap,
    hasInitialized,
    loadProject,
    navigate,
    projectId,
  ]);

  const node = useMemo(() => {
    if (!snapshot || !nodeId) {
      return null;
    }
    return (
      snapshot.tree_state.node_registry.find(
        (item) => item.node_id === nodeId,
      ) ?? null
    );
  }, [nodeId, snapshot]);

  usePlanningEventStream(
    projectId && node ? projectId : null,
    node ? node.node_id : null,
  );
  useAgentEventStream(
    projectId && node ? projectId : null,
    node ? node.node_id : null,
  );
  useAskSessionStream(
    projectId && node && activeTab === "ask" ? projectId : null,
    node && activeTab === "ask" ? node.node_id : null,
  );
  useChatSessionStream(
    projectId && node && activeTab === "execution" ? projectId : null,
    node && activeTab === "execution" ? node.node_id : null,
  );

  useEffect(() => {
    if (
      !projectId ||
      !nodeId ||
      !snapshot ||
      snapshot.project.id !== projectId ||
      !node
    ) {
      return;
    }
    if (selectedNodeId === nodeId) {
      return;
    }
    void selectNode(nodeId, true);
  }, [node?.node_id, nodeId, projectId, selectNode, selectedNodeId, snapshot]);

  useEffect(() => {
    if (hasInitialized && !isLoadingSnapshot && snapshot && !node) {
      navigate("/", { replace: true });
    }
  }, [hasInitialized, isLoadingSnapshot, navigate, node, snapshot]);

  useEffect(() => {
    if (!projectId || !nodeId || !node) {
      return;
    }
    const composerSeed =
      typeof (location.state as { composerSeed?: string } | null)
        ?.composerSeed === "string"
        ? ((location.state as { composerSeed?: string }).composerSeed ?? "")
        : "";
    if (!composerSeed.trim()) {
      return;
    }
    setComposerDraft(composerSeed);
    navigate(location.pathname, { replace: true, state: null });
  }, [
    location.pathname,
    location.state,
    navigate,
    node?.node_id,
    nodeId,
    projectId,
    setComposerDraft,
  ]);

  useEffect(() => {
    const requestedTab = (
      location.state as { activeTab?: RequestedTabId } | null
    )?.activeTab;
    if (requestedTab) {
      setActiveTab(resolveRequestedTab(requestedTab));
    }
  }, [location.state]);

  useEffect(() => {
    if (
      !nodeId ||
      !node ||
      node.status !== "ready" ||
      !chatSession ||
      chatSession.node_id !== nodeId
    ) {
      return;
    }
    if (chatSession.messages.length === 0 && !chatSession.active_turn_id) {
      return;
    }
    patchNodeStatus(nodeId, "in_progress");
  }, [chatSession, node, nodeId, patchNodeStatus]);

  useEffect(() => {
    if (
      !node ||
      (activeTab !== "planning" &&
        activeTab !== "task" &&
        activeTab !== "briefing" &&
        activeTab !== "spec" &&
        activeTab !== "execution")
    ) {
      return;
    }
    void loadNodeDocuments(node.node_id).catch(() => undefined);
  }, [activeTab, loadNodeDocuments, node]);

  useEffect(() => {
    const pendingRequest = chatSession?.pending_input_request;
    if (!pendingRequest) {
      setPlanInputDrafts({});
      setPlanInputError(null);
      setIsResolvingPlanInput(false);
      return;
    }
    setPlanInputDrafts((current) => {
      const next: Record<string, string> = {};
      pendingRequest.questions.forEach((question) => {
        if (current[question.id]) {
          next[question.id] = current[question.id];
        }
      });
      return next;
    });
    setPlanInputError(null);
  }, [chatSession?.pending_input_request]);

  if (
    isInitializing ||
    isLoadingSnapshot ||
    !hasInitialized ||
    !snapshot ||
    !projectId ||
    !nodeId ||
    !node
  ) {
    return (
      <div className={styles.loading}>Loading breadcrumb workspace...</div>
    );
  }

  const nodeDocuments = documentsByNode[node.node_id];
  const nodeActivity = agentActivityByNode[node.node_id];
  const executionState = nodeDocuments?.state;
  const pendingInputRequest = chatSession?.pending_input_request ?? null;
  const currentPlan = nodeDocuments?.plan?.content?.trim() ?? "";
  const canPlan =
    Boolean(
      executionState &&
      node.phase === "ready_for_execution" &&
      executionState.spec_confirmed &&
      executionState.brief_generation_status === "ready" &&
      executionState.plan_status !== "waiting_on_input" &&
      !chatSession?.active_turn_id,
    ) && !isPlanningAction;
  const canExecute =
    Boolean(
      executionState &&
      node.phase === "ready_for_execution" &&
      executionState.plan_status === "ready" &&
      executionState.bound_plan_spec_version ===
        executionState.active_spec_version &&
      executionState.bound_plan_brief_version ===
        executionState.brief_version &&
      executionState.bound_plan_input_version ===
        executionState.active_plan_input_version &&
      !chatSession?.active_turn_id,
    ) && !isExecutingAction;
  const canReplyToPlanner = false;
  let executionStatusText = "Confirm Spec before planning.";
  if (
    node.phase === "executing" &&
    executionState?.run_status === "completed"
  ) {
    executionStatusText =
      "Execution finished. Review the transcript and mark the node done when ready.";
  } else if (executionState?.run_status === "failed") {
    executionStatusText =
      "Execution failed safely. Re-run Plan when the contract is still current, then Execute again.";
  } else if (node.phase === "blocked_on_spec_question") {
    executionStatusText =
      "Planner found a contract change. Review the Spec before creating another ready plan.";
  } else if (executionState?.plan_status === "waiting_on_input") {
    executionStatusText =
      "Planner is waiting on a quick native input so it can finish the active plan turn.";
  } else if (executionState?.plan_status === "ready") {
    executionStatusText =
      "Plan is ready and bound to the current Brief, confirmed Spec, and plan-input version.";
  } else if (node.phase === "ready_for_execution") {
    executionStatusText =
      "Click Plan to let the agent self-check the contract and finish the execution plan.";
  }
  const planFailure =
    executionState?.last_agent_failure?.operation === "plan"
      ? executionState.last_agent_failure
      : null;
  const executionActivityCard = planFailure ? (
    <AgentActivityCard
      title="Execution Planning"
      status="Failed"
      tone="negative"
      message={planFailure.message || "The planner did not finish this turn."}
    />
  ) : executionState?.plan_status === "waiting_on_input" ? (
    <AgentActivityCard
      title="Execution Planning"
      status="Waiting on input"
      message="Answer the native planner prompt to continue the active planning turn."
    />
  ) : node.phase === "blocked_on_spec_question" ? (
    <AgentActivityCard
      title="Execution Planning"
      status="Spec review required"
      tone="negative"
      message={
        executionState?.spec_update_change_summary ||
        "Planner found a contract change that needs Spec review."
      }
    />
  ) : executionState?.plan_status === "generating" ||
    nodeActivity?.operation === "plan" ? (
    <AgentActivityCard
      title="Execution Planning"
      status={
        nodeActivity?.status === "operation_completed"
          ? "Completed"
          : "Planner is thinking"
      }
      tone={
        nodeActivity?.status === "operation_completed" ? "positive" : "neutral"
      }
      message={
        nodeActivity?.message ||
        (executionState?.plan_status === "ready"
          ? "The plan is ready to review."
          : "The planner is checking the contract and preparing the next turn.")
      }
    />
  ) : null;

  const canSubmitPlanInput = Boolean(
    pendingInputRequest &&
      pendingInputRequest.questions.every(
        (question) => (planInputDrafts[question.id] ?? "").trim().length > 0,
      ) &&
      !isResolvingPlanInput,
  );

  async function handleResolvePlanInput() {
    if (!projectId || !node || !pendingInputRequest || !canSubmitPlanInput) {
      return;
    }
    setIsResolvingPlanInput(true);
    setPlanInputError(null);
    try {
      await api.resolvePlanInput(projectId, node.node_id, pendingInputRequest.request_id, {
        thread_id: pendingInputRequest.thread_id,
        turn_id: pendingInputRequest.turn_id,
        answers: Object.fromEntries(
          pendingInputRequest.questions.map((question) => [
            question.id,
            { answers: [(planInputDrafts[question.id] ?? "").trim()] },
          ]),
        ),
      });
    } catch (error) {
      setPlanInputError(
        error instanceof Error ? error.message : "Could not resolve planner input.",
      );
      setIsResolvingPlanInput(false);
      return;
    }
  }

  const plannerInputModal = pendingInputRequest ? (
    <div className={styles.modalBackdrop} role="presentation">
      <section
        className={styles.modalCard}
        role="dialog"
        aria-modal="true"
        aria-labelledby="planner-input-title"
      >
        <div className={styles.modalHeader}>
          <p className={styles.modalEyebrow}>Planner Input</p>
          <h4 id="planner-input-title">One quick answer before the plan can finish</h4>
          <p>
            This response stays attached to the active planning turn. The planner
            will continue automatically after you submit.
          </p>
        </div>
        <div className={styles.modalBody}>
          {pendingInputRequest.questions.map((question) => {
            const answer = planInputDrafts[question.id] ?? "";
            const options = question.options ?? [];
            return (
              <article key={question.id} className={styles.modalQuestion}>
                <p className={styles.modalQuestionHeader}>{question.header}</p>
                <p className={styles.modalQuestionText}>{question.question}</p>
                {options.length > 0 ? (
                  <div className={styles.optionList}>
                    {options.map((option) => (
                      <label key={option.label} className={styles.optionItem}>
                        <input
                          type="radio"
                          name={question.id}
                          checked={answer === option.label}
                          onChange={() =>
                            setPlanInputDrafts((current) => ({
                              ...current,
                              [question.id]: option.label,
                            }))
                          }
                        />
                        <span>
                          <strong>{option.label}</strong>
                          {option.description ? ` ${option.description}` : ""}
                        </span>
                      </label>
                    ))}
                  </div>
                ) : null}
                {question.is_other || options.length === 0 ? (
                  <textarea
                    className={styles.modalTextarea}
                    rows={question.is_secret ? 2 : 3}
                    value={answer}
                    placeholder={
                      question.is_secret
                        ? "Enter your answer privately..."
                        : "Type your answer..."
                    }
                    onChange={(event) =>
                      setPlanInputDrafts((current) => ({
                        ...current,
                        [question.id]: event.target.value,
                      }))
                    }
                  />
                ) : null}
              </article>
            );
          })}
        </div>
        {planInputError ? <p className={styles.modalError}>{planInputError}</p> : null}
        <div className={styles.modalActions}>
          <button
            type="button"
            className={styles.startExecutionButton}
            disabled={!canSubmitPlanInput}
            onClick={() => void handleResolvePlanInput()}
          >
            {isResolvingPlanInput ? "Submitting..." : "Continue planning"}
          </button>
        </div>
      </section>
    </div>
  ) : null;

  return (
    <section className={styles.view}>
      <BreadcrumbHeader
        nodes={snapshot.tree_state.node_registry}
        nodeId={nodeId}
        onBack={() => navigate("/")}
      />
      <div className={styles.layout}>
        <aside className={styles.explorer}>
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`${styles.explorerItem} ${activeTab === tab.id ? styles.active : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </aside>
        <div className={styles.content}>
          {activeTab === "planning" ? (
            <PlanningPanel
              node={node}
              documents={nodeDocuments}
              activity={nodeActivity}
            />
          ) : null}
          {activeTab === "task" ? (
            <TaskPanel
              node={node}
              documents={nodeDocuments}
              isLoading={isLoadingDocuments}
              isUpdating={isUpdatingDocument}
              isConfirming={isConfirmingNode}
              activity={nodeActivity}
              onReload={() =>
                loadNodeDocuments(node.node_id).then(() => undefined)
              }
              onSave={(payload) => updateNodeTask(node.node_id, payload)}
              onConfirm={() => confirmTask(node.node_id)}
              onRetryBrief={() => confirmTask(node.node_id)}
              onOpenBrief={() => setActiveTab("briefing")}
              onOpenSpec={() => setActiveTab("spec")}
            />
          ) : null}
          {activeTab === "ask" ? (
            <AskPanel node={node} projectId={projectId} />
          ) : null}
          {activeTab === "briefing" ? (
            <BriefingPanel
              node={node}
              documents={nodeDocuments}
              isLoading={isLoadingDocuments}
              isRetrying={isConfirmingNode}
              activity={nodeActivity}
              onReload={() =>
                loadNodeDocuments(node.node_id).then(() => undefined)
              }
              onRetry={() => confirmTask(node.node_id)}
            />
          ) : null}
          {activeTab === "spec" ? (
            <SpecPanel
              node={node}
              documents={nodeDocuments}
              isLoading={isLoadingDocuments}
              isUpdating={isUpdatingDocument}
              isGenerating={isGeneratingSpec}
              isConfirming={isConfirmingNode}
              activity={nodeActivity}
              onReload={() =>
                loadNodeDocuments(node.node_id).then(() => undefined)
              }
              onSave={(payload) => updateNodeSpec(node.node_id, payload)}
              onGenerate={() => generateNodeSpec(node.node_id)}
              onConfirm={() => confirmSpec(node.node_id)}
            />
          ) : null}
          {activeTab === "execution" ? (
            <div className={styles.executionStack}>
              <div className={styles.placeholder}>
                <h3>Execution</h3>
                <p>{executionStatusText}</p>
                <div className={styles.executionActions}>
                  <button
                    type="button"
                    className={styles.startExecutionButton}
                    disabled={!canPlan}
                    onClick={async () => {
                      setIsPlanningAction(true);
                      try {
                        await startPlan(node.node_id);
                      } catch {
                        return;
                      } finally {
                        setIsPlanningAction(false);
                      }
                    }}
                  >
                    {isPlanningAction ? "Planning..." : "Plan"}
                  </button>
                  <button
                    type="button"
                    className={styles.secondaryExecutionButton}
                    disabled={!canExecute}
                    onClick={async () => {
                      setIsExecutingAction(true);
                      try {
                        await executeNode(node.node_id);
                      } catch {
                        return;
                      } finally {
                        setIsExecutingAction(false);
                      }
                    }}
                  >
                    {isExecutingAction ? "Executing..." : "Execute"}
                  </button>
                </div>
              </div>
              {executionActivityCard}
              {currentPlan ? (
                <div className={styles.planCard}>
                  <h4>Current Plan</h4>
                  <pre className={styles.planContent}>{currentPlan}</pre>
                </div>
              ) : null}
              {node.phase === "blocked_on_spec_question" &&
              executionState?.spec_update_change_summary ? (
                <section className={styles.specUpdateCard}>
                  <h4>Spec Review Handoff</h4>
                  <p>{executionState.spec_update_change_summary}</p>
                  {executionState.spec_update_recommended_next_step ? (
                    <p>
                      Next step: {executionState.spec_update_recommended_next_step}
                    </p>
                  ) : null}
                </section>
              ) : null}
              <ChatPanel
                node={node}
                projectId={projectId}
                composerEnabled={canReplyToPlanner}
                composerPlaceholder={
                  canReplyToPlanner
                    ? `Reply to the planner for ${node.title}...`
                    : "Planner input is handled through the native modal when needed."
                }
                emptyTitle="Plan Session"
                emptyHint={
                  executionState?.plan_status === "ready"
                    ? "The current plan is ready. Review it above, then click Execute."
                    : "Click Plan to start an execution planning turn for this node."
                }
              />
              {plannerInputModal}
            </div>
          ) : null}
          <div className={styles.footer}>
            <MarkDoneButton projectId={projectId} nodeId={nodeId} node={node} />
          </div>
        </div>
      </div>
    </section>
  );
}
