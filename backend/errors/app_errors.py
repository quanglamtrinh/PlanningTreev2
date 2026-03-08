class AppError(Exception):
    """Base class for all typed application errors."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


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


class NodeNotFound(AppError):
    def __init__(self, node_id: str) -> None:
        super().__init__("node_not_found", f"Node {node_id!r} not found.", 404)


class SplitNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("split_not_allowed", reason, 409)


class CompleteNotAllowed(AppError):
    def __init__(self, reason: str) -> None:
        super().__init__("complete_not_allowed", reason, 409)


class ChatTurnAlreadyActive(AppError):
    def __init__(self) -> None:
        super().__init__(
            "chat_turn_already_active",
            "A chat turn is already in progress for this node.",
            409,
        )


class AuthRequired(AppError):
    def __init__(self) -> None:
        super().__init__("auth_required", "Authentication required.", 401)
