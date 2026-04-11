from __future__ import annotations

from pathlib import Path


def test_workflow_v3_route_has_no_v2_query_runtime_or_adapter_dependencies() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow_v3_path = repo_root / "backend" / "routes" / "workflow_v3.py"
    content = workflow_v3_path.read_text(encoding="utf-8")

    forbidden_tokens = [
        "thread_query_service_v2",
        "thread_runtime_service_v2",
        "project_v2_snapshot_to_v3",
        "project_v2_envelope_to_v3",
    ]
    for token in forbidden_tokens:
        assert token not in content, f"Forbidden Phase-3 dependency remains in workflow_v3 route: {token}"
