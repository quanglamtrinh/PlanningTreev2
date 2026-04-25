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


def test_workflow_v3_state_mutation_routes_use_phase10_compat_adapter() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    workflow_v3_path = repo_root / "backend" / "routes" / "workflow_v3.py"
    content = workflow_v3_path.read_text(encoding="utf-8")

    assert "def _workflow_v3_adapter(request: Request)" in content
    assert "workflow_v3_compat_adapter" in content
    assert "WORKFLOW_V3_DEPRECATION_HEADERS" in content
    assert "execution_audit_workflow_service_v2" not in content

    workflow_segment = content.split('@router.get("/projects/{project_id}/nodes/{node_id}/workflow-state")', 1)[1]
    workflow_segment = workflow_segment.split('@router.get("/projects/{project_id}/events")', 1)[0]
    assert "_workflow_v3_adapter(request)" in workflow_segment
    assert "_workflow_service(request)" not in workflow_segment
    assert "execution_audit_workflow_service" not in workflow_segment
