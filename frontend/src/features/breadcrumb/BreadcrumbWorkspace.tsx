import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import {
  useAgentEventStream,
  useAskSessionStream,
  useChatSessionStream,
  usePlanningEventStream,
} from "../../api/hooks";
import {
  isAskConversationV2Enabled,
  isExecutionConversationV2Enabled,
  isPlanningConversationV2Enabled,
} from "../../config/featureFlags";
import { deriveConversationBusy } from "../conversation/model/deriveConversationBusy";
import { useAskConversation } from "../conversation/hooks/useAskConversation";
import { useConversationRequests } from "../conversation/hooks/useConversationRequests";
import { useExecutionConversation } from "../conversation/hooks/useExecutionConversation";
import { usePlanningConversation } from "../conversation/hooks/usePlanningConversation";
import { useAskStore } from "../../stores/ask-store";
import { useChatStore } from "../../stores/chat-store";
import { useConversationStore } from "../../stores/conversation-store";
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

function readComposerSeed(state: unknown): string {
  if (!state || typeof state !== "object") {
    return "";
  }
  const composerSeed = (state as { composerSeed?: unknown }).composerSeed;
  return typeof composerSeed === "string" ? composerSeed : "";
}

function clearComposerSeedFromLocationState(state: unknown): Record<string, unknown> | null {
  if (!state || typeof state !== "object") {
    return null;
  }
  const nextState = { ...(state as Record<string, unknown>) };
  delete nextState.composerSeed;
  return Object.keys(nextState).length > 0 ? nextState : null;
}

function hasLiveExecutionConversationActivity(
  conversation: ReturnType<typeof useExecutionConversation>["conversation"],
): boolean {
  if (!conversation) {
    return false;
  }
  const latestMessage =
    conversation.snapshot.messages[conversation.snapshot.messages.length - 1] ?? null;
  return (
    conversation.snapshot.record.active_stream_id !== null ||
    conversation.snapshot.record.status === "active" ||
    latestMessage?.status === "pending" ||
    latestMessage?.status === "streaming"
  );
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
  const setPlanningNodeBusyState = useProjectStore(
    (state) => state.setPlanningNodeBusyState,
  );
  const chatSession = useChatStore((state) => state.session);
  const setComposerDraft = useChatStore((state) => state.setComposerDraft);
  const setAskComposerDraft = useAskStore((state) => state.setComposerDraft);
  const setConversationComposerDraft = useConversationStore(
    (state) => state.setComposerDraft,
  );
  const setActiveSurface = useUIStore((state) => state.setActiveSurface);
  const executionConversationV2Enabled = isExecutionConversationV2Enabled();
  const askConversationV2Enabled = isAskConversationV2Enabled();
  const planningConversationV2Enabled = isPlanningConversationV2Enabled();
  const appliedComposerSeedTokenRef = useRef<string | null>(null);
  const managedPlanningBusyNodeIdRef = useRef<string | null>(null);

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

  // Legacy planning transcript/history is non-authoritative on the planning v2 host path.
  usePlanningEventStream(
    planningConversationV2Enabled ? null : projectId && node ? projectId : null,
    planningConversationV2Enabled ? null : node ? node.node_id : null,
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
  const askConversation = useAskConversation({
    projectId: projectId ?? null,
    nodeId: node?.node_id ?? null,
    enabled:
      askConversationV2Enabled &&
      activeTab === "ask" &&
      Boolean(projectId && node?.node_id),
  });
  const executionConversation = useExecutionConversation({
    projectId: projectId ?? null,
    nodeId: node?.node_id ?? null,
    enabled:
      executionConversationV2Enabled &&
      activeTab === "execution" &&
      Boolean(projectId && node?.node_id),
  });
  const executionConversationRequests = useConversationRequests({
    projectId: executionConversationV2Enabled ? projectId ?? null : null,
    nodeId: executionConversationV2Enabled ? node?.node_id ?? null : null,
    conversation: executionConversationV2Enabled
      ? executionConversation.conversation
      : null,
    refresh: executionConversation.refresh,
  });
  const planningConversation = usePlanningConversation({
    projectId: projectId ?? null,
    nodeId: node?.node_id ?? null,
    enabled:
      planningConversationV2Enabled &&
      activeTab === "planning" &&
      Boolean(projectId && node?.node_id),
  });

  useEffect(() => {
    const managedNodeId =
      planningConversationV2Enabled && activeTab === "planning" && node?.node_id
        ? node.node_id
        : null;
    const previousManagedNodeId = managedPlanningBusyNodeIdRef.current;

    if (previousManagedNodeId && previousManagedNodeId !== managedNodeId) {
      setPlanningNodeBusyState(previousManagedNodeId, false);
    }

    managedPlanningBusyNodeIdRef.current = managedNodeId;

    if (!managedNodeId) {
      return;
    }

    setPlanningNodeBusyState(
      managedNodeId,
      deriveConversationBusy(planningConversation.conversation?.snapshot),
    );
  }, [
    activeTab,
    node?.node_id,
    planningConversation.conversation?.snapshot,
    planningConversationV2Enabled,
    setPlanningNodeBusyState,
  ]);

  useEffect(() => {
    return () => {
      const managedNodeId = managedPlanningBusyNodeIdRef.current;
      if (!managedNodeId) {
        return;
      }
      setPlanningNodeBusyState(managedNodeId, false);
      managedPlanningBusyNodeIdRef.current = null;
    };
  }, [setPlanningNodeBusyState]);

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
    const composerSeed = readComposerSeed(location.state);
    if (!composerSeed.trim()) {
      return;
    }

    const seedToken = `${location.key}:${composerSeed}`;
    if (appliedComposerSeedTokenRef.current === seedToken) {
      return;
    }

    const shouldSeedExecutionV2 =
      executionConversationV2Enabled && activeTab === "execution";
    const shouldSeedAskV2 = askConversationV2Enabled && activeTab === "ask";

    if (shouldSeedExecutionV2) {
      if (!executionConversation.conversationId) {
        return;
      }
      setConversationComposerDraft(
        executionConversation.conversationId,
        composerSeed,
      );
    } else if (shouldSeedAskV2) {
      if (!askConversation.conversationId) {
        return;
      }
      setConversationComposerDraft(
        askConversation.conversationId,
        composerSeed,
      );
    } else if (activeTab === "ask") {
      setAskComposerDraft(composerSeed);
    } else {
      setComposerDraft(composerSeed);
    }

    appliedComposerSeedTokenRef.current = seedToken;
    navigate(location.pathname, {
      replace: true,
      state: clearComposerSeedFromLocationState(location.state),
    });
  }, [
    activeTab,
    askConversation.conversationId,
    askConversationV2Enabled,
    executionConversation.conversationId,
    executionConversationV2Enabled,
    location.pathname,
    location.key,
    location.state,
    navigate,
    node?.node_id,
    nodeId,
    projectId,
    setAskComposerDraft,
    setConversationComposerDraft,
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
    if (!nodeId || !node || node.status !== "ready") {
      return;
    }

    if (executionConversationV2Enabled) {
      if (activeTab !== "execution") {
        return;
      }
      if (!hasLiveExecutionConversationActivity(executionConversation.conversation)) {
        return;
      }
      patchNodeStatus(nodeId, "in_progress");
      return;
    }

    if (!chatSession || chatSession.node_id !== nodeId) {
      return;
    }
    if (chatSession.messages.length === 0 && !chatSession.active_turn_id) {
      return;
    }
    patchNodeStatus(nodeId, "in_progress");
  }, [
    activeTab,
    chatSession,
    executionConversation.conversation,
    executionConversationV2Enabled,
    node,
    nodeId,
    patchNodeStatus,
  ]);

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
    const pendingRequest = executionConversationV2Enabled
      ? executionConversationRequests.activeRequest?.requestKind === "user_input"
        ? {
            request_id: executionConversationRequests.activeRequest.requestId,
            thread_id: executionConversationRequests.activeRequest.threadId,
            turn_id: executionConversationRequests.activeRequest.turnId,
            questions: executionConversationRequests.activeRequest.questions.map((question) => ({
              id: question.id,
              header: question.header,
              question: question.question,
              is_other: question.isOther,
              is_secret: question.isSecret,
              options: question.options,
            })),
          }
        : null
      : chatSession?.pending_input_request;
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
  }, [
    chatSession?.pending_input_request,
    executionConversationRequests.activeRequest,
    executionConversationV2Enabled,
  ]);

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
  const pendingInputRequest = executionConversationV2Enabled
    ? executionConversationRequests.activeRequest?.requestKind === "user_input"
      ? {
          request_id: executionConversationRequests.activeRequest.requestId,
          thread_id: executionConversationRequests.activeRequest.threadId,
          turn_id: executionConversationRequests.activeRequest.turnId,
          questions: executionConversationRequests.activeRequest.questions.map((question) => ({
            id: question.id,
            header: question.header,
            question: question.question,
            is_other: question.isOther,
            is_secret: question.isSecret,
            options: question.options,
          })),
        }
      : null
    : chatSession?.pending_input_request ?? null;
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
  const canMessageExecution =
    node.phase === "executing" &&
    executionState?.run_status === "executing";
  const legacyExecutionComposerPlaceholder =
    "Planner input is handled through the native modal when needed.";
  const executionComposerPlaceholder = executionConversationV2Enabled
    ? pendingInputRequest
      ? legacyExecutionComposerPlaceholder
      : canMessageExecution
        ? `Message ${node.title}...`
        : executionState?.plan_status === "ready"
          ? "Click Execute to start the execution conversation."
          : "Click Plan to prepare execution."
    : legacyExecutionComposerPlaceholder;
  const executionEmptyTitle = executionConversationV2Enabled
    ? "Execution Conversation"
    : "Plan Session";
  const executionEmptyHint = executionConversationV2Enabled
    ? pendingInputRequest
      ? "Planner input is handled through the native modal when needed."
      : executionState?.run_status === "executing"
        ? "Execution messages will appear here as the current run progresses."
        : executionState?.plan_status === "ready"
          ? "The current plan is ready. Review it above, then click Execute."
          : "Click Plan to start an execution planning turn for this node."
    : executionState?.plan_status === "ready"
      ? "The current plan is ready. Review it above, then click Execute."
      : "Click Plan to start an execution planning turn for this node.";
  const visibleExecutionConversation = executionConversationV2Enabled
    ? {
        conversationId: executionConversation.conversationId,
        conversation: executionConversation.conversation,
        bootstrapStatus: executionConversation.bootstrapStatus,
        bootstrapError: executionConversation.bootstrapError,
        send: executionConversation.send,
      }
    : undefined;
  const visibleAskConversation = askConversationV2Enabled
    ? {
        conversationId: askConversation.conversationId,
        conversation: askConversation.conversation,
        bootstrapStatus: askConversation.bootstrapStatus,
        bootstrapError: askConversation.bootstrapError,
        send: askConversation.send,
        refresh: askConversation.refresh,
      }
    : undefined;
  const visiblePlanningConversation = planningConversationV2Enabled
    ? {
        conversationId: planningConversation.conversationId,
        conversation: planningConversation.conversation,
        bootstrapStatus: planningConversation.bootstrapStatus,
        bootstrapError: planningConversation.bootstrapError,
      }
    : undefined;
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
      !(executionConversationV2Enabled
        ? executionConversationRequests.isSubmitting
        : isResolvingPlanInput),
  );

  async function handleResolvePlanInput() {
    if (!projectId || !node || !pendingInputRequest || !canSubmitPlanInput) {
      return;
    }
    if (executionConversationV2Enabled) {
      setPlanInputError(null);
      try {
        await executionConversationRequests.submitUserInputResponse({
          requestId: pendingInputRequest.request_id,
          threadId: pendingInputRequest.thread_id,
          turnId: pendingInputRequest.turn_id,
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
      }
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

  const visiblePlanInputError = executionConversationV2Enabled
    ? executionConversationRequests.submitError ?? planInputError
    : planInputError;
  const isPlanInputSubmitting = executionConversationV2Enabled
    ? executionConversationRequests.isSubmitting
    : isResolvingPlanInput;

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
        {visiblePlanInputError ? <p className={styles.modalError}>{visiblePlanInputError}</p> : null}
        <div className={styles.modalActions}>
          <button
            type="button"
            className={styles.startExecutionButton}
            disabled={!canSubmitPlanInput}
            onClick={() => void handleResolvePlanInput()}
          >
            {isPlanInputSubmitting ? "Submitting..." : "Continue planning"}
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
              planningConversation={visiblePlanningConversation}
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
            <AskPanel
              node={node}
              projectId={projectId}
              askConversation={visibleAskConversation}
            />
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
                composerEnabled={
                  executionConversationV2Enabled
                    ? canMessageExecution
                    : false
                }
                composerPlaceholder={executionComposerPlaceholder}
                emptyTitle={executionEmptyTitle}
                emptyHint={executionEmptyHint}
                executionConversation={visibleExecutionConversation}
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
