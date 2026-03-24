from __future__ import annotations

from backend.services.node_detail_service import derive_workflow_summary_from_artifacts


def test_workflow_summary_defaults_to_frame_before_confirmation() -> None:
    summary = derive_workflow_summary_from_artifacts(
        {"revision": 0, "confirmed_revision": 0, "confirmed_at": None},
        None,
        {"source_frame_revision": 0, "confirmed_at": None},
    )

    assert summary == {
        "frame_confirmed": False,
        "active_step": "frame",
        "spec_confirmed": False,
    }


def test_workflow_summary_reports_clarify_when_questions_remain() -> None:
    summary = derive_workflow_summary_from_artifacts(
        {"revision": 1, "confirmed_revision": 1, "confirmed_at": "2026-03-22T00:00:00Z"},
        {"confirmed_at": None, "questions": [{"field_name": "target platform"}]},
        {"source_frame_revision": 0, "confirmed_at": None},
    )

    assert summary == {
        "frame_confirmed": True,
        "active_step": "clarify",
        "spec_confirmed": False,
    }


def test_workflow_summary_reports_spec_when_confirmed_frame_has_no_questions() -> None:
    summary = derive_workflow_summary_from_artifacts(
        {"revision": 2, "confirmed_revision": 2, "confirmed_at": "2026-03-22T00:00:00Z"},
        {"confirmed_at": "2026-03-22T00:05:00Z", "questions": []},
        {"source_frame_revision": 2, "confirmed_at": None},
    )

    assert summary == {
        "frame_confirmed": True,
        "active_step": "spec",
        "spec_confirmed": False,
    }
