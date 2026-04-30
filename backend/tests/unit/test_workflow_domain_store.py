from __future__ import annotations

import json

from backend.services.project_service import ProjectService


def _project_id(storage, workspace_root) -> str:
    return ProjectService(storage).attach_project_folder(str(workspace_root))["project"]["id"]


def test_workflow_domain_store_persists_node_state_under_workflow_core_v2(storage, workspace_root) -> None:
    project_id = _project_id(storage, workspace_root)
    store = storage.workflow_domain_store

    execution = store.write_execution(
        project_id,
        "node-a",
        {
            "status": "review_pending",
            "initial_sha": " sha256:initial ",
            "head_sha": "sha256:head",
            "changed_files": [{"path": "app.py"}],
            "auto_review": {"summary": "Looks good"},
        },
    )
    review = store.add_review_checkpoint(
        project_id,
        "review-a",
        sha="sha256:accepted",
        summary="done",
        source_node_id="node-a",
    )

    assert execution["status"] == "review_pending"
    assert execution["initial_sha"] == "sha256:initial"
    assert store.read_execution(project_id, "node-a")["auto_review"]["summary"] == "Looks good"
    assert review["checkpoints"][0]["source_node_id"] == "node-a"

    node_payload = json.loads(
        (workspace_root / ".planningtree" / "workflow_core_v2" / "node-a.json").read_text(
            encoding="utf-8"
        )
    )
    review_payload = json.loads(
        (workspace_root / ".planningtree" / "workflow_core_v2" / "review-a.json").read_text(
            encoding="utf-8"
        )
    )
    assert node_payload["executionProjection"]["status"] == "review_pending"
    assert review_payload["reviewPackage"]["checkpoints"][0]["sha"] == "sha256:accepted"


def test_workflow_domain_store_persists_project_artifact_jobs_under_workflow_core_v2(storage, workspace_root) -> None:
    project_id = _project_id(storage, workspace_root)
    store = storage.workflow_domain_store

    state = store.write_split_jobs(
        project_id,
        {
            "active_job": {
                "job_id": "job-1",
                "node_id": "node-a",
                "mode": "workflow",
                "started_at": "2026-04-29T00:00:00Z",
            },
            "last_error": None,
            "last_completed": None,
        },
    )

    assert state["active_job"]["job_id"] == "job-1"
    assert store.read_split_jobs(project_id)["active_job"]["mode"] == "workflow"

    payload = json.loads(
        (workspace_root / ".planningtree" / "workflow_core_v2" / "artifact_jobs.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["split"]["active_job"]["node_id"] == "node-a"
