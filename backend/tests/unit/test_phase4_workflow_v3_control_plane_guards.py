from __future__ import annotations

from pathlib import Path


def test_workflow_v3_control_plane_routes_exist() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow_v3_path = repo_root / "backend" / "routes" / "workflow_v3.py"
    content = workflow_v3_path.read_text(encoding="utf-8")

    required_routes = [
        '/projects/{project_id}/nodes/{node_id}/workflow-state',
        '/projects/{project_id}/nodes/{node_id}/workflow/finish-task',
        '/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-execution',
        '/projects/{project_id}/nodes/{node_id}/workflow/review-in-audit',
        '/projects/{project_id}/nodes/{node_id}/workflow/mark-done-from-audit',
        '/projects/{project_id}/nodes/{node_id}/workflow/improve-in-execution',
        '/projects/{project_id}/events',
    ]
    for route in required_routes:
        assert route in content, f"Missing Phase-4 control-plane route in workflow_v3 router: {route}"


def test_workflow_v3_prefers_canonical_workflow_service_state() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow_v3_path = repo_root / "backend" / "routes" / "workflow_v3.py"
    content = workflow_v3_path.read_text(encoding="utf-8")

    assert "def _workflow_service(request: Request)" in content
    assert "execution_audit_workflow_service" in content
    # Keep only one fallback reference to legacy alias inside the helper.
    assert content.count("execution_audit_workflow_service_v2") == 1
