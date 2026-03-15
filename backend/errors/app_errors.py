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


class SpecGenerationNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("spec_generation_not_allowed", reason, 409)


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


class ConversationStreamMismatch(AppError):
    def __init__(self) -> None:
        super().__init__(
            "conversation_stream_mismatch",
            "The requested stream is no longer the active live stream for this conversation.",
            409,
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
