from __future__ import annotations

from backend.business.workflow_v2.errors import WorkflowV2NotImplementedError
from backend.business.workflow_v2.models import ThreadBinding, ThreadRole


class ThreadBindingServiceV2:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._args = args
        self._kwargs = kwargs

    def ensure_thread(
        self,
        *,
        project_id: str,
        node_id: str,
        role: ThreadRole,
        model: str | None = None,
        model_provider: str | None = None,
        force_rebase: bool = False,
    ) -> ThreadBinding:
        raise WorkflowV2NotImplementedError("thread_binding.ensure_thread")

