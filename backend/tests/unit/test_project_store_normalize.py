from __future__ import annotations

import pytest

from backend.storage.storage import Storage


@pytest.fixture
def project_store(storage):
    return storage.project_store


def test_normalize_review_node_id_empty_string_becomes_none(project_store):
    node = project_store._normalize_node({
        "node_id": "n1", "review_node_id": "",
    })
    assert node["review_node_id"] is None


def test_normalize_review_node_id_whitespace_becomes_none(project_store):
    node = project_store._normalize_node({
        "node_id": "n1", "review_node_id": "   ",
    })
    assert node["review_node_id"] is None


def test_normalize_review_node_id_trimmed(project_store):
    node = project_store._normalize_node({
        "node_id": "n1", "review_node_id": " rev-1 ",
    })
    assert node["review_node_id"] == "rev-1"


def test_normalize_review_node_id_valid_passthrough(project_store):
    node = project_store._normalize_node({
        "node_id": "n1", "review_node_id": "abc123",
    })
    assert node["review_node_id"] == "abc123"


def test_normalize_review_node_id_non_string_becomes_none(project_store):
    node = project_store._normalize_node({
        "node_id": "n1", "review_node_id": 42,
    })
    assert node["review_node_id"] is None


def test_normalize_review_node_id_absent_becomes_none(project_store):
    node = project_store._normalize_node({
        "node_id": "n1",
    })
    assert node["review_node_id"] is None
