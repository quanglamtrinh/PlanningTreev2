from __future__ import annotations

import json

import pytest

from backend.storage.storage import Storage


@pytest.fixture
def chat_store(storage):
    return storage.chat_state_store


@pytest.fixture
def project_id(storage, workspace_root):
    from backend.services.project_service import ProjectService

    svc = ProjectService(storage)
    snap = svc.attach_project_folder(str(workspace_root))
    return snap["project"]["id"]


def test_read_session_default_thread_role(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1")
    assert session["thread_role"] == "ask_planning"


def test_read_session_with_explicit_role(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1", thread_role="audit")
    assert session["thread_role"] == "audit"


def test_write_and_read_with_thread_role(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1", thread_role="audit")
    session["thread_id"] = "thread-audit-1"
    chat_store.write_session(project_id, "node1", session, thread_role="audit")

    loaded = chat_store.read_session(project_id, "node1", thread_role="audit")
    assert loaded["thread_id"] == "thread-audit-1"
    assert loaded["thread_role"] == "audit"

    # ask_planning session should be separate
    ask = chat_store.read_session(project_id, "node1", thread_role="ask_planning")
    assert ask["thread_id"] is None
    assert ask["thread_role"] == "ask_planning"


def test_separate_sessions_per_role(chat_store, project_id):
    for role in ("ask_planning", "audit", "execution"):
        session = chat_store.read_session(project_id, "node1", thread_role=role)
        session["thread_id"] = f"thread-{role}"
        chat_store.write_session(project_id, "node1", session, thread_role=role)

    for role in ("ask_planning", "audit", "execution"):
        loaded = chat_store.read_session(project_id, "node1", thread_role=role)
        assert loaded["thread_id"] == f"thread-{role}"
        assert loaded["thread_role"] == role


def test_clear_session_with_role(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1", thread_role="audit")
    session["thread_id"] = "t1"
    chat_store.write_session(project_id, "node1", session, thread_role="audit")

    cleared = chat_store.clear_session(project_id, "node1", thread_role="audit")
    assert cleared["thread_id"] is None
    assert cleared["thread_role"] == "audit"


def test_normalize_preserves_lineage_fields(chat_store, project_id):
    session = chat_store.read_session(project_id, "node-lineage", thread_role="audit")
    session.update(
        {
            "thread_id": "audit-thread-1",
            "forked_from_thread_id": "root-thread-1",
            "forked_from_node_id": "root-node",
            "forked_from_role": "audit",
            "fork_reason": "review_bootstrap",
            "lineage_root_thread_id": "root-thread-1",
        }
    )
    chat_store.write_session(project_id, "node-lineage", session, thread_role="audit")

    loaded = chat_store.read_session(project_id, "node-lineage", thread_role="audit")
    assert loaded["thread_id"] == "audit-thread-1"
    assert loaded["forked_from_thread_id"] == "root-thread-1"
    assert loaded["forked_from_node_id"] == "root-node"
    assert loaded["forked_from_role"] == "audit"
    assert loaded["fork_reason"] == "review_bootstrap"
    assert loaded["lineage_root_thread_id"] == "root-thread-1"


def test_normalize_defaults_missing_lineage_fields(chat_store, project_id):
    path = chat_store.path(project_id, "legacy-node", "audit")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "thread_id": "legacy-thread",
                "thread_role": "audit",
                "active_turn_id": None,
                "messages": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    loaded = chat_store.read_session(project_id, "legacy-node", thread_role="audit")
    assert loaded["thread_id"] == "legacy-thread"
    assert loaded["forked_from_thread_id"] is None
    assert loaded["forked_from_node_id"] is None
    assert loaded["forked_from_role"] is None
    assert loaded["fork_reason"] is None
    assert loaded["lineage_root_thread_id"] is None


def test_invalid_thread_role_falls_back_to_default(chat_store, project_id):
    session = chat_store.read_session(project_id, "node1", thread_role="invalid_role")
    assert session["thread_role"] == "ask_planning"


def test_flat_file_migration(chat_store, project_id):
    """Old flat chat/{node_id}.json should be migrated to chat/{node_id}/ask_planning.json."""
    flat_path = chat_store._flat_path(project_id, "migrate_node")
    flat_path.parent.mkdir(parents=True, exist_ok=True)
    flat_data = {
        "thread_id": "old-thread",
        "active_turn_id": None,
        "messages": [],
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:00Z",
    }
    flat_path.write_text(json.dumps(flat_data), encoding="utf-8")
    assert flat_path.exists()

    # Reading should trigger migration
    session = chat_store.read_session(project_id, "migrate_node")
    assert session["thread_id"] == "old-thread"
    assert session["thread_role"] == "ask_planning"

    # Flat file should be gone, directory should exist
    assert not flat_path.exists()
    role_dir = chat_store._role_dir(project_id, "migrate_node")
    assert role_dir.exists()
    assert (role_dir / "ask_planning.json").exists()


def test_migration_when_directory_exists_but_ask_planning_missing(chat_store, project_id):
    """If directory exists (e.g. audit created first) but ask_planning.json is missing,
    flat file should still be migrated into ask_planning.json."""
    flat_path = chat_store._flat_path(project_id, "node2")
    flat_path.parent.mkdir(parents=True, exist_ok=True)
    flat_data = {"thread_id": "old-history", "active_turn_id": None, "messages": [],
                 "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}
    flat_path.write_text(json.dumps(flat_data), encoding="utf-8")

    # Create the directory first (simulating an audit session created earlier)
    role_dir = chat_store._role_dir(project_id, "node2")
    role_dir.mkdir(parents=True, exist_ok=True)

    session = chat_store.read_session(project_id, "node2")
    # Should have migrated the flat file data
    assert session["thread_id"] == "old-history"
    assert session["thread_role"] == "ask_planning"

    # Flat file should be gone, ask_planning.json should exist
    assert not flat_path.exists()
    assert (role_dir / "ask_planning.json").exists()


def test_migration_skipped_when_both_flat_and_ask_planning_exist(chat_store, project_id):
    """If both flat file and ask_planning.json exist, ask_planning.json wins
    and flat file is kept intact (not silently deleted)."""
    flat_path = chat_store._flat_path(project_id, "node3")
    flat_path.parent.mkdir(parents=True, exist_ok=True)
    flat_data = {"thread_id": "old-flat", "active_turn_id": None, "messages": [],
                 "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z"}
    flat_path.write_text(json.dumps(flat_data), encoding="utf-8")

    # Also create the ask_planning.json with different data
    role_dir = chat_store._role_dir(project_id, "node3")
    role_dir.mkdir(parents=True, exist_ok=True)
    new_data = {"thread_id": "new-dir", "thread_role": "ask_planning",
                "active_turn_id": None, "messages": [],
                "created_at": "2026-02-01T00:00:00Z", "updated_at": "2026-02-01T00:00:00Z"}
    (role_dir / "ask_planning.json").write_text(json.dumps(new_data), encoding="utf-8")

    session = chat_store.read_session(project_id, "node3")
    # Directory version wins
    assert session["thread_id"] == "new-dir"

    # Flat file is kept intact (not silently deleted)
    assert flat_path.exists()


def test_role_path_structure(chat_store, project_id):
    path = chat_store.path(project_id, "node1", "audit")
    assert path.name == "audit.json"
    assert path.parent.name == "node1"


def test_integration_to_audit_migration(chat_store, project_id):
    role_dir = chat_store._role_dir(project_id, "review-node")
    role_dir.mkdir(parents=True, exist_ok=True)
    integration_path = role_dir / "integration.json"
    integration_path.write_text(
        json.dumps(
            {
                "thread_id": "legacy-review-thread",
                "thread_role": "integration",
                "active_turn_id": None,
                "messages": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    loaded = chat_store.read_session(project_id, "review-node", thread_role="audit")
    audit_path = chat_store.path(project_id, "review-node", "audit")

    assert loaded["thread_id"] == "legacy-review-thread"
    assert loaded["thread_role"] == "audit"
    assert loaded["fork_reason"] == "review_bootstrap_legacy_migrated"
    assert audit_path.exists()
    assert not integration_path.exists()
    assert json.loads(audit_path.read_text(encoding="utf-8"))["thread_role"] == "audit"


def test_integration_alias_resolves_to_audit(chat_store, project_id):
    session = chat_store.read_session(project_id, "review-alias", thread_role="audit")
    session["thread_id"] = "audit-thread"
    chat_store.write_session(project_id, "review-alias", session, thread_role="audit")

    loaded = chat_store.read_session(project_id, "review-alias", thread_role="integration")
    assert loaded["thread_id"] == "audit-thread"
    assert loaded["thread_role"] == "audit"


def test_integration_write_alias(chat_store, project_id):
    session = chat_store.read_session(project_id, "review-write", thread_role="integration")
    session["thread_id"] = "audit-via-alias"
    saved = chat_store.write_session(project_id, "review-write", session, thread_role="integration")

    audit_path = chat_store.path(project_id, "review-write", "audit")
    integration_path = chat_store._role_dir(project_id, "review-write") / "integration.json"

    assert saved["thread_role"] == "audit"
    assert audit_path.exists()
    assert not integration_path.exists()
    assert json.loads(audit_path.read_text(encoding="utf-8"))["thread_id"] == "audit-via-alias"


def test_integration_clear_alias(chat_store, project_id):
    session = chat_store.read_session(project_id, "review-clear", thread_role="audit")
    session["thread_id"] = "audit-thread"
    chat_store.write_session(project_id, "review-clear", session, thread_role="audit")

    cleared = chat_store.clear_session(project_id, "review-clear", thread_role="integration")
    audit_path = chat_store.path(project_id, "review-clear", "audit")
    integration_path = chat_store._role_dir(project_id, "review-clear") / "integration.json"

    assert cleared["thread_role"] == "audit"
    assert cleared["thread_id"] is None
    assert audit_path.exists()
    assert not integration_path.exists()
    assert json.loads(audit_path.read_text(encoding="utf-8"))["thread_id"] is None


def test_migration_idempotent_when_audit_exists(chat_store, project_id):
    role_dir = chat_store._role_dir(project_id, "review-both")
    role_dir.mkdir(parents=True, exist_ok=True)
    integration_path = role_dir / "integration.json"
    audit_path = role_dir / "audit.json"
    integration_path.write_text(
        json.dumps(
            {
                "thread_id": "legacy-integration-thread",
                "thread_role": "integration",
                "active_turn_id": None,
                "messages": [],
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    audit_path.write_text(
        json.dumps(
            {
                "thread_id": "audit-wins-thread",
                "thread_role": "audit",
                "active_turn_id": None,
                "messages": [],
                "created_at": "2026-02-01T00:00:00Z",
                "updated_at": "2026-02-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )

    loaded = chat_store.read_session(project_id, "review-both", thread_role="integration")
    assert loaded["thread_id"] == "audit-wins-thread"
    assert loaded["thread_role"] == "audit"
    assert integration_path.exists()
    assert audit_path.exists()
    assert json.loads(audit_path.read_text(encoding="utf-8"))["thread_id"] == "audit-wins-thread"


def test_message_items_round_trip(chat_store, project_id):
    session = chat_store.read_session(project_id, "node-items", thread_role="audit")
    session["messages"] = [
        {
            "message_id": "msg-1",
            "role": "assistant",
            "content": "done",
            "status": "completed",
            "error": None,
            "turn_id": "turn-1",
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "items": [
                {
                    "item_id": "assistant_text",
                    "item_type": "assistant_text",
                    "status": "completed",
                    "started_at": "2026-01-01T00:00:00Z",
                    "completed_at": "2026-01-01T00:00:01Z",
                    "lifecycle": [
                        {
                            "phase": "delta",
                            "timestamp": "2026-01-01T00:00:00Z",
                            "text": "done",
                        }
                    ],
                }
            ],
        }
    ]
    chat_store.write_session(project_id, "node-items", session, thread_role="audit")
    loaded = chat_store.read_session(project_id, "node-items", thread_role="audit")
    assert loaded["messages"][0]["items"][0]["item_type"] == "assistant_text"
