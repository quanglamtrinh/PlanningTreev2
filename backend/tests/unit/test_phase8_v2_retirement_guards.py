from __future__ import annotations

from pathlib import Path


def test_main_does_not_mount_v2_routes() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    main_path = repo_root / "backend" / "main.py"
    content = main_path.read_text(encoding="utf-8")

    assert "include_router(chat_v2.router, prefix=\"/v2\")" not in content
    assert "include_router(workflow_v2.router, prefix=\"/v2\")" not in content


def test_main_mounts_product_routes_with_v4_prefix_only() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    main_path = repo_root / "backend" / "main.py"
    content = main_path.read_text(encoding="utf-8")

    assert "prefix=\"/v1\"" not in content
    assert "prefix=\"/v2\"" not in content
    assert "prefix=\"/v3\"" not in content
    assert 'app.include_router(product_router, prefix="/v4")' in content
    assert ("API" + "_PREFIX") not in content


def test_main_does_not_publish_v2_conversation_runtime_aliases() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    main_path = repo_root / "backend" / "main.py"
    content = main_path.read_text(encoding="utf-8")

    forbidden_aliases = [
        "app.state.thread_query_service_v2",
        "app.state.thread_runtime_service_v2",
        "app.state.conversation_event_broker_v2",
        "app.state.request_ledger_service_v2",
    ]
    for alias in forbidden_aliases:
        assert alias not in content, f"Found removed v2 alias in main wiring: {alias}"


def test_auth_middleware_protects_v4_prefix() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    middleware_path = repo_root / "backend" / "middleware" / "auth_token.py"
    content = middleware_path.read_text(encoding="utf-8")

    assert "_PROTECTED_PREFIXES = (\"/v4/\",)" in content
    assert ("API" + "_PREFIX") not in content
    assert "\"/v1/\"" not in content
    assert "\"/v2/\"" not in content
