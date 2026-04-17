from __future__ import annotations


class AppError(Exception):
    """Base class for all typed application errors."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class InvalidRequest(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_request", message, 400)


class InvalidProjectFolder(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_project_folder", reason, 400)


class InvalidWorkspaceRoot(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("invalid_workspace_root", reason, 400)


class WorkspaceNotConfigured(AppError):
    def __init__(self) -> None:
        super().__init__(
            "workspace_not_configured",
            "Workspace not configured. Set a base workspace root in settings.",
            412,
        )


class ProjectNotFound(AppError):
    def __init__(self, project_id: str) -> None:
        super().__init__("project_not_found", f"Project {project_id!r} not found.", 404)


class WorkspaceFileNotFound(AppError):
    def __init__(self, message: str = "File not found.") -> None:
        super().__init__("workspace_file_not_found", message, 404)


class LegacyProjectUnsupported(AppError):
    def __init__(self, project_id: str) -> None:
        super().__init__(
            "legacy_project_unsupported",
            (
                f"Project {project_id!r} uses removed legacy planning/thread content storage. "
                "Delete or recreate the project before using this build."
            ),
            409,
        )


class InvalidProjectId(AppError):
    def __init__(self, project_id: str) -> None:
        super().__init__(
            "invalid_project_id",
            f"Project id {project_id!r} must be a 32-character lowercase hex string.",
            400,
        )


class NodeNotFound(AppError):
    def __init__(self, node_id: str) -> None:
        super().__init__("node_not_found", f"Node {node_id!r} not found.", 404)


class NodeCreateNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("node_create_not_allowed", reason, 409)


class NodeUpdateNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("node_update_not_allowed", reason, 409)


class ConfirmationNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("confirmation_not_allowed", reason, 409)


class FrameGenerationNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("frame_generation_not_allowed", reason, 409)


class FrameGenerationBackendUnavailable(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("frame_generation_backend_unavailable", reason, 503)


class ClarifyGenerationNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("clarify_generation_not_allowed", reason, 409)


class ClarifyGenerationBackendUnavailable(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("clarify_generation_backend_unavailable", reason, 503)


class SpecGenerationNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("spec_generation_not_allowed", reason, 409)


class SpecGenerationBackendUnavailable(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("spec_generation_backend_unavailable", reason, 503)


class BriefGenerationNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("brief_generation_not_allowed", reason, 409)


class BriefGenerationInvalidResponse(AppError):
    def __init__(self, issues: list[str] | None = None) -> None:
        details = "; ".join(issue for issue in (issues or []) if issue.strip())
        message = "AI brief generation returned invalid output after retry."
        if details:
            message = f"{message} {details}"
        super().__init__("brief_generation_invalid_response", message, 502)


class SpecGenerationInvalidResponse(AppError):
    def __init__(self, issues: list[str] | None = None) -> None:
        details = "; ".join(issue for issue in (issues or []) if issue.strip())
        message = "AI spec generation returned invalid output after retry."
        if details:
            message = f"{message} {details}"
        super().__init__("spec_generation_invalid_response", message, 502)


class PlanExecuteNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("plan_execute_not_allowed", reason, 409)


class PlanExecuteInvalidResponse(AppError):
    def __init__(self, issues: list[str] | None = None) -> None:
        details = "; ".join(issue for issue in (issues or []) if issue.strip())
        message = "AI planning or execution returned invalid output after retry."
        if details:
            message = f"{message} {details}"
        super().__init__("plan_execute_invalid_response", message, 502)


class PlanInputResolutionNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("plan_input_resolution_not_allowed", reason, 409)


class CompleteNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("complete_not_allowed", reason, 409)


class SplitNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("split_not_allowed", reason, 409)


class SplitBackendUnavailable(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("split_backend_unavailable", reason, 503)


class SplitInvalidResponse(AppError):
    def __init__(self, issues: list[str] | None = None) -> None:
        details = "; ".join(issue for issue in (issues or []) if str(issue).strip())
        message = "AI split returned invalid structured output after retry."
        if details:
            message = f"{message} {details}"
        super().__init__("split_invalid_response", message, 502)


class ProjectResetNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("project_reset_not_allowed", reason, 409)


class ChatTurnAlreadyActive(AppError):
    def __init__(self) -> None:
        super().__init__(
            "chat_turn_already_active",
            "A chat turn is already in progress for this node.",
            409,
        )


class ChatBackendUnavailable(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("chat_backend_unavailable", reason, 503)


class ChatNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("chat_not_allowed", reason, 409)


class ConversationStreamMismatch(AppError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            "conversation_stream_mismatch",
            message or "The requested stream is no longer the active live stream for this conversation.",
            409,
        )


class ConversationV3Missing(AppError):
    def __init__(self) -> None:
        super().__init__(
            "conversation_v3_missing",
            "Conversation V3 snapshot is missing for this thread.",
            409,
        )


class ConversationPersistenceUnavailable(AppError):
    def __init__(self) -> None:
        super().__init__(
            "conversation_persistence_unavailable",
            "Execution conversation persistence is temporarily unavailable. Retry the request.",
            503,
        )


class ExecutionAuditRehearsalWorkspaceUnsafe(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            "execution_audit_v2_rehearsal_workspace_unsafe",
            reason,
            412,
        )


class AuthRequired(AppError):
    def __init__(self) -> None:
        super().__init__("auth_required", "Authentication required.", 401)


class AskTurnAlreadyActive(AppError):
    def __init__(self) -> None:
        super().__init__(
            "ask_turn_already_active",
            "An ask turn is already in progress for this node.",
            409,
        )


class AskBlockedByPlanningActive(AppError):
    def __init__(self) -> None:
        super().__init__(
            "ask_blocked_by_planning_active",
            "Cannot mutate ask state while planning is active for this node.",
            409,
        )


class MergeBlockedBySplit(AppError):
    def __init__(self, node_id: str) -> None:
        super().__init__(
            "merge_blocked_by_split",
            f"Cannot merge delta context: node {node_id!r} has been split.",
            409,
        )


class MergePlanningThreadUnavailable(AppError):
    def __init__(self, node_id: str) -> None:
        super().__init__(
            "merge_planning_thread_unavailable",
            f"Cannot merge delta context for node {node_id!r} because the planning thread is unavailable. Retry the merge.",
            503,
        )


class PacketMutationBlockedBySplit(AppError):
    def __init__(self, action: str, node_id: str) -> None:
        super().__init__(
            "packet_mutation_blocked_by_split",
            f"Cannot {action} delta context packet: node {node_id!r} has already been split.",
            409,
        )


class PacketNotFound(AppError):
    def __init__(self, packet_id: str) -> None:
        super().__init__(
            "packet_not_found",
            f"Delta context packet {packet_id!r} not found.",
            404,
        )


class InvalidPacketTransition(AppError):
    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            "invalid_packet_transition",
            f"Cannot transition packet from '{from_status}' to '{to_status}'.",
            409,
        )


class AskThreadReadOnly(AppError):
    def __init__(self) -> None:
        super().__init__(
            "ask_thread_read_only",
            "Ask thread is read-only because this node is no longer mutable.",
            409,
        )


class AskV3Disabled(AppError):
    def __init__(self) -> None:
        super().__init__(
            "ask_v3_disabled",
            "Ask V3 APIs are disabled by server configuration.",
            409,
        )


class AskIdempotencyPayloadConflict(AppError):
    def __init__(self) -> None:
        super().__init__(
            "ask_idempotency_payload_conflict",
            "idempotencyKey was already used with a different ask payload.",
            409,
        )


class ShapingFrozen(AppError):
    def __init__(self, action: str = "shaping action") -> None:
        super().__init__(
            "shaping_frozen",
            f"Cannot perform {action}: shaping is frozen after Finish Task.",
            409,
        )


class ThreadReadOnly(AppError):
    def __init__(self, thread_role: str, reason: str = "") -> None:
        detail = f" {reason}" if reason else ""
        super().__init__(
            "thread_read_only",
            f"Thread '{thread_role}' is read-only.{detail}",
            409,
        )


class FinishTaskNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("finish_task_not_allowed", reason, 400)


class ReviewNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("review_not_allowed", reason, 400)


class SiblingActivationNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("sibling_activation_not_allowed", reason, 400)


class GitCheckpointError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("git_checkpoint_error", message, 500)


class GitInitNotAllowed(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("git_init_not_allowed", message, 400)


class ResetWorkspaceNotAllowed(AppError):
    def __init__(self, message: str) -> None:
        super().__init__("reset_workspace_not_allowed", message, 400)
