from __future__ import annotations

import pytest

from backend.storage.storage import Storage


@pytest.fixture
def review_store(storage):
    return storage.review_state_store


@pytest.fixture
def project_id(storage, workspace_root):
    from backend.services.project_service import ProjectService

    svc = ProjectService(storage)
    snap = svc.attach_project_folder(str(workspace_root))
    return snap["project"]["id"]


# ── Basic read/write ─────────────────────────────────────────────

def test_read_returns_none_when_no_file(review_store, project_id):
    assert review_store.read_state(project_id, "nonexistent") is None


def test_write_and_read_round_trip(review_store, project_id):
    state = {
        "checkpoints": [
            {"label": "K0", "sha": "sha256:baseline", "summary": None,
             "source_node_id": None, "accepted_at": "2026-03-23T10:00:00Z"},
        ],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [
            {"index": 2, "title": "Sibling B", "objective": "Do B",
             "materialized_node_id": None},
        ],
    }
    review_store.write_state(project_id, "review1", state)

    loaded = review_store.read_state(project_id, "review1")
    assert loaded is not None
    assert len(loaded["checkpoints"]) == 1
    assert loaded["checkpoints"][0]["label"] == "K0"
    assert loaded["rollup"]["status"] == "pending"
    assert len(loaded["pending_siblings"]) == 1
    assert loaded["pending_siblings"][0]["title"] == "Sibling B"


# ── Checkpoint operations ────────────────────────────────────────

def test_add_checkpoint(review_store, project_id):
    state = {
        "checkpoints": [
            {"label": "K0", "sha": "sha256:baseline", "summary": None,
             "source_node_id": None, "accepted_at": "2026-03-23T10:00:00Z"},
        ],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [],
    }
    review_store.write_state(project_id, "review1", state)

    updated = review_store.add_checkpoint(
        project_id, "review1",
        sha="sha256:after-1a",
        summary="1.A completed successfully",
        source_node_id="node-1a",
    )

    assert len(updated["checkpoints"]) == 2
    k1 = updated["checkpoints"][1]
    assert k1["label"] == "K1"
    assert k1["sha"] == "sha256:after-1a"
    assert k1["summary"] == "1.A completed successfully"
    assert k1["source_node_id"] == "node-1a"
    assert isinstance(k1["accepted_at"], str)


def test_checkpoint_progression_k0_k1_k2(review_store, project_id):
    state = {
        "checkpoints": [
            {"label": "K0", "sha": "sha256:base", "summary": None,
             "source_node_id": None, "accepted_at": "2026-01-01T00:00:00Z"},
        ],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [],
    }
    review_store.write_state(project_id, "review1", state)

    review_store.add_checkpoint(project_id, "review1", sha="sha256:k1", summary="S1", source_node_id="n1")
    updated = review_store.add_checkpoint(project_id, "review1", sha="sha256:k2", summary="S2", source_node_id="n2")

    assert len(updated["checkpoints"]) == 3
    assert [cp["label"] for cp in updated["checkpoints"]] == ["K0", "K1", "K2"]


# ── Rollup operations ────────────────────────────────────────────

def test_set_rollup_to_ready(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [],
    }
    review_store.write_state(project_id, "review1", state)

    updated = review_store.set_rollup(project_id, "review1", status="ready")
    assert updated["rollup"]["status"] == "ready"
    assert updated["rollup"]["accepted_at"] is None


def test_set_rollup_to_accepted(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "ready", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [],
    }
    review_store.write_state(project_id, "review1", state)

    updated = review_store.set_rollup(
        project_id, "review1",
        status="accepted",
        summary="All good",
        sha="sha256:final",
    )
    assert updated["rollup"]["status"] == "accepted"
    assert updated["rollup"]["summary"] == "All good"
    assert updated["rollup"]["sha"] == "sha256:final"
    assert isinstance(updated["rollup"]["accepted_at"], str)


# ── Sibling operations ───────────────────────────────────────────

def test_get_next_pending_sibling(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [
            {"index": 2, "title": "B", "objective": "Do B", "materialized_node_id": None},
            {"index": 3, "title": "C", "objective": "Do C", "materialized_node_id": None},
        ],
    }
    review_store.write_state(project_id, "review1", state)

    sib = review_store.get_next_pending_sibling(project_id, "review1")
    assert sib is not None
    assert sib["index"] == 2
    assert sib["title"] == "B"


def test_get_next_pending_sibling_skips_materialized(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [
            {"index": 2, "title": "B", "objective": "Do B", "materialized_node_id": "node-b"},
            {"index": 3, "title": "C", "objective": "Do C", "materialized_node_id": None},
        ],
    }
    review_store.write_state(project_id, "review1", state)

    sib = review_store.get_next_pending_sibling(project_id, "review1")
    assert sib is not None
    assert sib["index"] == 3


def test_get_next_pending_sibling_returns_none_when_all_materialized(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [
            {"index": 2, "title": "B", "objective": "Do B", "materialized_node_id": "node-b"},
        ],
    }
    review_store.write_state(project_id, "review1", state)

    assert review_store.get_next_pending_sibling(project_id, "review1") is None


def test_mark_sibling_materialized(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [
            {"index": 2, "title": "B", "objective": "Do B", "materialized_node_id": None},
            {"index": 3, "title": "C", "objective": "Do C", "materialized_node_id": None},
        ],
    }
    review_store.write_state(project_id, "review1", state)

    updated = review_store.mark_sibling_materialized(project_id, "review1", index=2, node_id="new-b")
    sibs = updated["pending_siblings"]
    assert sibs[0]["materialized_node_id"] == "new-b"
    assert sibs[1]["materialized_node_id"] is None


# ── Normalization ────────────────────────────────────────────────

def test_normalize_non_dict_returns_default(review_store):
    result = review_store._normalize_state("not a dict")
    assert result["checkpoints"] == []
    assert result["rollup"]["status"] == "pending"
    assert result["pending_siblings"] == []


def test_normalize_invalid_rollup_status(review_store):
    result = review_store._normalize_rollup({"status": "bogus"})
    assert result["status"] == "pending"


def test_normalize_drops_invalid_checkpoints(review_store):
    result = review_store._normalize_state({
        "checkpoints": [
            "not a dict",
            {"label": "K0"},  # missing sha
            {"label": "K0", "sha": "sha256:ok"},  # valid
        ],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [],
    })
    assert len(result["checkpoints"]) == 1
    assert result["checkpoints"][0]["sha"] == "sha256:ok"


def test_normalize_drops_invalid_pending_siblings(review_store):
    result = review_store._normalize_state({
        "checkpoints": [],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [
            {"index": 0, "title": "Bad", "objective": "Zero index"},  # index < 1
            {"index": 2, "title": "", "objective": "Empty title"},  # empty title
            {"index": 3, "title": "Good", "objective": "Valid"},  # valid
        ],
    })
    assert len(result["pending_siblings"]) == 1
    assert result["pending_siblings"][0]["index"] == 3


# ── Rollup state machine enforcement ─────────────────────────────

def test_rollup_backward_transition_accepted_to_ready_rejected(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "accepted", "summary": "done", "sha": "sha256:final",
                   "accepted_at": "2026-03-23T12:00:00Z"},
        "pending_siblings": [],
    }
    review_store.write_state(project_id, "review1", state)

    from backend.errors.app_errors import InvalidRequest
    with pytest.raises(InvalidRequest, match="Invalid rollup transition"):
        review_store.set_rollup(project_id, "review1", status="ready")


def test_rollup_backward_transition_ready_to_pending_rejected(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "ready", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [],
    }
    review_store.write_state(project_id, "review1", state)

    from backend.errors.app_errors import InvalidRequest
    with pytest.raises(InvalidRequest, match="Invalid rollup transition"):
        review_store.set_rollup(project_id, "review1", status="pending")


def test_rollup_skip_transition_pending_to_accepted_rejected(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "pending", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [],
    }
    review_store.write_state(project_id, "review1", state)

    from backend.errors.app_errors import InvalidRequest
    with pytest.raises(InvalidRequest, match="Invalid rollup transition"):
        review_store.set_rollup(project_id, "review1", status="accepted",
                                summary="s", sha="sha256:x")


def test_rollup_accepted_without_summary_rejected(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "ready", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [],
    }
    review_store.write_state(project_id, "review1", state)

    from backend.errors.app_errors import InvalidRequest
    with pytest.raises(InvalidRequest, match="requires a non-empty summary"):
        review_store.set_rollup(project_id, "review1", status="accepted", sha="sha256:x")


def test_rollup_accepted_without_sha_rejected(review_store, project_id):
    state = {
        "checkpoints": [],
        "rollup": {"status": "ready", "summary": None, "sha": None, "accepted_at": None},
        "pending_siblings": [],
    }
    review_store.write_state(project_id, "review1", state)

    from backend.errors.app_errors import InvalidRequest
    with pytest.raises(InvalidRequest, match="requires a non-empty sha"):
        review_store.set_rollup(project_id, "review1", status="accepted", summary="done")
