from __future__ import annotations

import json

import pytest

from backend.services.project_service import ProjectService


@pytest.fixture
def workflow_store(storage):
    return storage.workflow_state_store


@pytest.fixture
def project_id(storage, workspace_root):
    svc = ProjectService(storage)
    snap = svc.attach_project_folder(str(workspace_root))
    return snap["project"]["id"]


def test_default_state_includes_latest_commit_none(workflow_store):
    state = workflow_store.default_state("node-1")
    assert "latestCommit" in state
    assert state["latestCommit"] is None


def test_latest_commit_round_trip_keeps_canonical_keys(workflow_store, project_id):
    state = workflow_store.default_state("node-1")
    state["latestCommit"] = {
        "sourceAction": "split",
        "initialSha": "abc123",
        "headSha": "def456",
        "commitMessage": "pt(1): split task",
        "committed": True,
        "recordedAt": "2026-04-04T10:00:00Z",
    }

    written = workflow_store.write_state(project_id, "node-1", state)
    loaded = workflow_store.read_state(project_id, "node-1")
    assert loaded is not None
    assert loaded["latestCommit"] == written["latestCommit"]
    assert loaded["latestCommit"] == {
        "sourceAction": "split",
        "initialSha": "abc123",
        "headSha": "def456",
        "commitMessage": "pt(1): split task",
        "committed": True,
        "recordedAt": "2026-04-04T10:00:00Z",
    }

    raw = json.loads(workflow_store.path(project_id, "node-1").read_text(encoding="utf-8"))
    assert "latestCommit" in raw
    assert "latest_commit" not in raw
    assert set(raw["latestCommit"].keys()) == {
        "sourceAction",
        "initialSha",
        "headSha",
        "commitMessage",
        "committed",
        "recordedAt",
    }


def test_normalize_latest_commit_accepts_snake_case_input(workflow_store):
    normalized = workflow_store._normalize_state(
        {
            "node_id": "node-1",
            "latest_commit": {
                "source_action": "mark_done_from_execution",
                "initial_sha": "  abc123  ",
                "head_sha": "  def456  ",
                "commit_message": "  pt(1): done task  ",
                "committed": False,
                "recorded_at": "  2026-04-04T10:00:00Z  ",
            },
        },
        node_id="node-1",
    )
    assert normalized["latestCommit"] == {
        "sourceAction": "mark_done_from_execution",
        "initialSha": "abc123",
        "headSha": "def456",
        "commitMessage": "pt(1): done task",
        "committed": False,
        "recordedAt": "2026-04-04T10:00:00Z",
    }


def test_normalize_latest_commit_invalid_source_action_becomes_none(workflow_store):
    normalized = workflow_store._normalize_state(
        {
            "latestCommit": {
                "sourceAction": "unexpected_action",
                "initialSha": "abc123",
            }
        },
        node_id="node-1",
    )
    assert normalized["latestCommit"] == {
        "sourceAction": None,
        "initialSha": "abc123",
        "headSha": None,
        "commitMessage": None,
        "committed": None,
        "recordedAt": None,
    }


def test_normalize_latest_commit_non_bool_committed_becomes_none(workflow_store):
    normalized = workflow_store._normalize_state(
        {
            "latestCommit": {
                "sourceAction": "review_in_audit",
                "committed": "true",
                "headSha": "def456",
            }
        },
        node_id="node-1",
    )
    assert normalized["latestCommit"] == {
        "sourceAction": "review_in_audit",
        "initialSha": None,
        "headSha": "def456",
        "commitMessage": None,
        "committed": None,
        "recordedAt": None,
    }


def test_normalize_latest_commit_empty_fields_collapse_to_none(workflow_store):
    normalized = workflow_store._normalize_state(
        {
            "latestCommit": {
                "sourceAction": " ",
                "initialSha": "   ",
                "headSha": "",
                "commitMessage": " ",
                "committed": 1,
                "recordedAt": "  ",
            }
        },
        node_id="node-1",
    )
    assert normalized["latestCommit"] is None


def test_legacy_payload_without_latest_commit_is_compatible(workflow_store):
    normalized = workflow_store._normalize_state(
        {
            "node_id": "node-legacy",
            "workflow_phase": "execution_running",
            "accepted_sha": "abc123",
        },
        node_id="fallback-node",
    )
    assert normalized["nodeId"] == "node-legacy"
    assert normalized["workflowPhase"] == "execution_running"
    assert normalized["acceptedSha"] == "abc123"
    assert normalized["latestCommit"] is None
