from __future__ import annotations

from backend.conversation.domain.types_v3 import MiniJournalBoundaryTypeV3

_BOUNDARY_TYPES_ALWAYS_CHECKPOINT: tuple[MiniJournalBoundaryTypeV3, ...] = (
    "turn_completed",
    "turn_failed",
    "waiting_user_input",
    "eviction",
)


class ThreadCheckpointPolicyV3:
    def __init__(self, *, timer_checkpoint_ms: int = 5000) -> None:
        self._timer_checkpoint_ms = max(250, int(timer_checkpoint_ms))

    @property
    def timer_checkpoint_ms(self) -> int:
        return self._timer_checkpoint_ms

    def should_checkpoint(
        self,
        boundary_type: str | None,
        elapsed_ms: int,
        dirty_events_count: int,
    ) -> bool:
        normalized_boundary = str(boundary_type or "").strip()
        if normalized_boundary in _BOUNDARY_TYPES_ALWAYS_CHECKPOINT:
            return True
        if normalized_boundary == "timer_checkpoint":
            return True
        if int(dirty_events_count) <= 0:
            return False
        return int(elapsed_ms) >= self._timer_checkpoint_ms
