from __future__ import annotations

import pytest

from backend.storage.storage import Storage


@pytest.fixture
def exec_store(storage):
    return storage.execution_state_store


@pytest.fixture
def project_id(storage, workspace_root):
    from backend.services.project_service import ProjectService

    svc = ProjectService(storage)
    snap = svc.attach_project_folder(str(workspace_root))
    return snap["project"]["id"]


def test_read_returns_none_when_no_file(exec_store, project_id):
    result = exec_store.read_state(project_id, "nonexistent")
    assert result is None


def test_exists_returns_false_when_no_file(exec_store, project_id):
    assert exec_store.exists(project_id, "nonexistent") is False


def test_write_and_read_round_trip(exec_store, project_id):
    state = {
        "status": "executing",
        "initial_sha": "sha256:abc123",
        "head_sha": None,
        "started_at": "2026-03-23T10:00:00Z",
        "completed_at": None,
    }
    exec_store.write_state(project_id, "node1", state)

    loaded = exec_store.read_state(project_id, "node1")
    assert loaded is not None
    assert loaded["status"] == "executing"
    assert loaded["initial_sha"] == "sha256:abc123"
    assert loaded["head_sha"] is None
    assert loaded["started_at"] == "2026-03-23T10:00:00Z"
    assert loaded["completed_at"] is None


def test_exists_returns_true_after_write(exec_store, project_id):
    state = {
        "status": "executing",
        "initial_sha": "sha256:abc",
        "head_sha": None,
        "started_at": "2026-03-23T10:00:00Z",
        "completed_at": None,
    }
    exec_store.write_state(project_id, "node1", state)
    assert exec_store.exists(project_id, "node1") is True


def test_update_state_to_completed(exec_store, project_id):
    state = {
        "status": "executing",
        "initial_sha": "sha256:abc",
        "head_sha": None,
        "started_at": "2026-03-23T10:00:00Z",
        "completed_at": None,
    }
    exec_store.write_state(project_id, "node1", state)

    state["status"] = "completed"
    state["head_sha"] = "sha256:def456"
    state["completed_at"] = "2026-03-23T11:00:00Z"
    exec_store.write_state(project_id, "node1", state)

    loaded = exec_store.read_state(project_id, "node1")
    assert loaded["status"] == "completed"
    assert loaded["head_sha"] == "sha256:def456"
    assert loaded["completed_at"] == "2026-03-23T11:00:00Z"
    assert loaded["initial_sha"] == "sha256:abc"


def test_normalize_invalid_status_defaults_to_idle(exec_store):
    result = exec_store._normalize_state({"status": "bogus"})
    assert result["status"] == "idle"


def test_normalize_non_dict_returns_default(exec_store):
    result = exec_store._normalize_state("not a dict")
    assert result["status"] == "idle"
    assert result["initial_sha"] is None
    assert result["head_sha"] is None
    assert result["started_at"] is None
    assert result["completed_at"] is None


def test_normalize_strips_whitespace(exec_store):
    result = exec_store._normalize_state({
        "status": "completed",
        "initial_sha": "  sha256:abc  ",
        "head_sha": "  sha256:def  ",
        "started_at": "  2026-03-23T10:00:00Z  ",
        "completed_at": "  2026-03-23T11:00:00Z  ",
    })
    assert result["initial_sha"] == "sha256:abc"
    assert result["head_sha"] == "sha256:def"
    assert result["started_at"] == "2026-03-23T10:00:00Z"
    assert result["completed_at"] == "2026-03-23T11:00:00Z"


def test_normalize_empty_strings_become_none(exec_store):
    result = exec_store._normalize_state({
        "status": "idle",
        "initial_sha": "   ",
        "head_sha": "",
        "started_at": "",
        "completed_at": "  ",
    })
    assert result["initial_sha"] is None
    assert result["head_sha"] is None
    assert result["started_at"] is None
    assert result["completed_at"] is None


def test_all_valid_statuses_accepted(exec_store):
    for status in ("idle", "executing", "completed", "review_pending", "review_accepted"):
        result = exec_store._normalize_state({"status": status})
        assert result["status"] == status


def test_separate_nodes_have_independent_state(exec_store, project_id):
    exec_store.write_state(project_id, "node1", {
        "status": "executing", "initial_sha": "sha1",
        "head_sha": None, "started_at": "2026-01-01T00:00:00Z", "completed_at": None,
    })
    exec_store.write_state(project_id, "node2", {
        "status": "completed", "initial_sha": "sha2",
        "head_sha": "sha3", "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T01:00:00Z",
    })

    s1 = exec_store.read_state(project_id, "node1")
    s2 = exec_store.read_state(project_id, "node2")
    assert s1["status"] == "executing"
    assert s2["status"] == "completed"
