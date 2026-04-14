from __future__ import annotations

from backend.conversation.services.thread_checkpoint_policy_v3 import ThreadCheckpointPolicyV3


def test_thread_checkpoint_policy_v3_boundary_always_checkpoints() -> None:
    policy = ThreadCheckpointPolicyV3(timer_checkpoint_ms=5000)
    assert policy.should_checkpoint("turn_completed", elapsed_ms=0, dirty_events_count=0) is True
    assert policy.should_checkpoint("turn_failed", elapsed_ms=0, dirty_events_count=0) is True
    assert policy.should_checkpoint("waiting_user_input", elapsed_ms=0, dirty_events_count=0) is True
    assert policy.should_checkpoint("eviction", elapsed_ms=0, dirty_events_count=0) is True


def test_thread_checkpoint_policy_v3_timer_requires_dirty_events() -> None:
    policy = ThreadCheckpointPolicyV3(timer_checkpoint_ms=5000)
    assert policy.should_checkpoint(None, elapsed_ms=6000, dirty_events_count=0) is False
    assert policy.should_checkpoint(None, elapsed_ms=1000, dirty_events_count=3) is False
    assert policy.should_checkpoint(None, elapsed_ms=6000, dirty_events_count=3) is True
