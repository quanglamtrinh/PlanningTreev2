from __future__ import annotations

import pytest

from backend.storage.node_files import (
    create_node_directory,
    default_state,
    empty_briefing,
    empty_spec,
    empty_task,
    load_all,
    parse_md_sections,
    read_briefing,
    read_spec,
    read_state,
    read_task,
    render_md_sections,
    write_briefing,
    write_spec,
    write_state,
    write_task,
)


def test_parse_md_sections_basic() -> None:
    text = "# Task\n\n## Title\nBuild thing\n\n## Purpose\nFor demo\n"
    result = parse_md_sections(text)
    assert result == {"Title": "Build thing", "Purpose": "For demo"}


def test_parse_md_sections_empty() -> None:
    assert parse_md_sections("") == {}


def test_parse_md_sections_no_subsections() -> None:
    assert parse_md_sections("# Task\nSome content\n") == {}


def test_parse_md_sections_empty_section() -> None:
    text = "# Task\n\n## Title\n\n## Purpose\nHello\n"
    result = parse_md_sections(text)
    assert result["Title"] == ""
    assert result["Purpose"] == "Hello"


def test_parse_md_sections_multiline_content() -> None:
    text = "# Spec\n\n## 1. Business / Product Contract\n- Item 1\n- Item 2\n\nMore text\n"
    result = parse_md_sections(text)
    assert result["1. Business / Product Contract"] == "- Item 1\n- Item 2\n\nMore text"


def test_parse_md_sections_keeps_deeper_headings_in_content() -> None:
    text = "# Task\n\n## Purpose\nLine 1\n### Detail\nLine 2\n"
    result = parse_md_sections(text)
    assert result["Purpose"] == "Line 1\n### Detail\nLine 2"


def test_parse_md_sections_special_characters() -> None:
    text = "# Task\n\n## Title\nBuild `thing` with **bold** & symbols\n"
    result = parse_md_sections(text)
    assert result["Title"] == "Build `thing` with **bold** & symbols"


def test_parse_md_sections_duplicate_heading_raises() -> None:
    text = "# Task\n\n## Title\nOne\n\n## Title\nTwo\n"
    with pytest.raises(ValueError):
        parse_md_sections(text)


def test_render_md_sections_basic() -> None:
    sections = {"Title": "Foo", "Purpose": "Bar"}
    result = render_md_sections("Task", sections)
    assert "# Task" in result
    assert "## Title\nFoo" in result
    assert "## Purpose\nBar" in result


def test_render_md_sections_empty_content() -> None:
    sections = {"Title": "", "Purpose": "Bar"}
    result = render_md_sections("Task", sections)
    assert "## Title\n" in result


def test_task_round_trip(tmp_path) -> None:
    task = {"title": "Build UI", "purpose": "For demo", "responsibility": "Catalog page"}
    write_task(tmp_path, task)
    assert read_task(tmp_path) == task

    content = (tmp_path / "task.md").read_text(encoding="utf-8")
    assert "## Title" in content
    assert "Build UI" in content


def test_briefing_round_trip(tmp_path) -> None:
    briefing = {
        "node_snapshot": {
            "node_summary": "Keep simple",
            "why_this_node_exists_now": "Browse only",
            "current_focus": "Focus on the current slice",
        },
        "active_inherited_context": {
            "active_goals_from_parent": ["Ship the slice"],
            "active_constraints_from_parent": ["Stay in workspace"],
            "active_decisions_in_force": ["Use FastAPI"],
        },
        "accepted_upstream_facts": {
            "accepted_outputs": ["React + TS"],
            "available_artifacts": ["spec.md"],
            "confirmed_dependencies": ["sqlite"],
        },
        "runtime_state": {
            "status": "ready",
            "completed_so_far": [],
            "current_blockers": [],
            "next_best_action": "Draft spec",
        },
        "pending_escalations": {
            "open_risks": ["None"],
            "pending_user_decisions": [],
            "fallback_direction_if_unanswered": "Stay inside the current scope.",
        },
    }
    write_briefing(tmp_path, briefing)
    assert read_briefing(tmp_path) == briefing

    content = (tmp_path / "briefing.md").read_text(encoding="utf-8")
    assert "### Node Summary" in content
    assert "- Ship the slice" in content


def test_spec_round_trip(tmp_path) -> None:
    spec = {
        "mission": {
            "goal": "Show catalog",
            "success_outcome": "Catalog page",
            "implementation_level": "working",
        },
        "scope": {
            "must_do": ["Show catalog"],
            "must_not_do": ["Do not add checkout"],
            "deferred_work": [],
        },
        "constraints": {
            "hard_constraints": ["Use existing schema"],
            "change_budget": "Keep edits local.",
            "touch_boundaries": ["frontend/src/features/catalog"],
            "external_dependencies": [],
        },
        "autonomy": {
            "allowed_decisions": ["Local UI choices"],
            "requires_confirmation": ["Scope expansion"],
            "default_policy_when_unclear": "ask_user",
        },
        "verification": {
            "acceptance_checks": ["Page loads"],
            "definition_of_done": "Catalog works end-to-end.",
            "evidence_expected": ["Screenshot"],
        },
        "execution_controls": {
            "quality_profile": "standard",
            "tooling_limits": ["workspace only"],
            "output_expectation": "concise progress updates",
            "conflict_policy": "reopen_spec",
            "missing_decision_policy": "reopen_spec",
        },
        "assumptions": {
            "assumptions_in_force": ["Seeded data OK"],
        },
    }
    write_spec(tmp_path, spec)
    assert read_spec(tmp_path) == spec

    content = (tmp_path / "spec.md").read_text(encoding="utf-8")
    assert "### Goal" in content
    assert "### Hard Constraints" in content


def test_state_round_trip(tmp_path) -> None:
    state = {
        "phase": "awaiting_brief",
        "task_confirmed": True,
        "briefing_confirmed": False,
        "brief_generation_status": "ready",
        "brief_version": 1,
        "spec_generated": False,
        "spec_generation_status": "idle",
        "spec_confirmed": False,
        "planning_thread_id": "thread_abc",
        "execution_thread_id": "",
        "ask_thread_id": "",
        "planning_thread_forked_from_node": "node_xyz",
        "planning_thread_bootstrapped_at": "2026-03-12T00:00:00+00:00",
        "chat_session_id": "",
    }
    write_state(tmp_path, state)
    loaded = read_state(tmp_path)
    for key, value in state.items():
        assert loaded[key] == value

    content = (tmp_path / "state.yaml").read_text(encoding="utf-8")
    assert "phase: awaiting_brief" in content
    assert "task_confirmed: true" in content


def test_read_task_rejects_unknown_top_level_heading(tmp_path) -> None:
    (tmp_path / "task.md").write_text(
        "# Task\n\n## Title\nA\n\n## Purpose\nB\n\n## Extra\nC\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        read_task(tmp_path)


def test_read_briefing_rejects_missing_required_section(tmp_path) -> None:
    (tmp_path / "briefing.md").write_text("# Brief\n\n## Node Snapshot\nA\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_briefing(tmp_path)


def test_empty_task() -> None:
    assert empty_task() == {"title": "", "purpose": "", "responsibility": ""}


def test_empty_briefing() -> None:
    briefing = empty_briefing()
    assert briefing["node_snapshot"]["node_summary"] == ""
    assert briefing["active_inherited_context"]["active_goals_from_parent"] == []


def test_empty_spec() -> None:
    spec = empty_spec()
    assert spec["mission"]["goal"] == ""
    assert spec["scope"]["must_do"] == []


def test_default_state() -> None:
    state = default_state()
    assert state["phase"] == "planning"
    assert state["task_confirmed"] is False
    assert state["brief_generation_started_at"] == ""
    assert state["spec_generation_status"] == "idle"
    assert state["spec_generation_started_at"] == ""


def test_read_state_fills_defaults(tmp_path) -> None:
    (tmp_path / "state.yaml").write_text("phase: executing\n", encoding="utf-8")
    state = read_state(tmp_path)
    assert state["phase"] == "executing"
    assert state["task_confirmed"] is False
    assert state["spec_generation_status"] == "idle"
    assert state["planning_thread_id"] == ""


def test_read_state_missing_file(tmp_path) -> None:
    with pytest.raises(FileNotFoundError):
        read_state(tmp_path)


def test_read_state_empty_file(tmp_path) -> None:
    (tmp_path / "state.yaml").write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        read_state(tmp_path)


def test_read_state_malformed_yaml(tmp_path) -> None:
    (tmp_path / "state.yaml").write_text("phase: [\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_state(tmp_path)


def test_read_state_non_mapping_yaml(tmp_path) -> None:
    (tmp_path / "state.yaml").write_text("- planning\n- executing\n", encoding="utf-8")
    with pytest.raises(ValueError):
        read_state(tmp_path)


def test_create_node_directory_and_load_all(tmp_path) -> None:
    node_dir = tmp_path / "test_node"
    task = {"title": "Test", "purpose": "Testing", "responsibility": "Unit test"}
    create_node_directory(node_dir, task, empty_briefing(), empty_spec(), default_state())

    assert node_dir.exists()
    assert (node_dir / "task.md").exists()
    assert (node_dir / "briefing.md").exists()
    assert (node_dir / "spec.md").exists()
    assert (node_dir / "state.yaml").exists()

    docs = load_all(node_dir)
    assert docs["task"] == task
    assert docs["brief"]["node_snapshot"]["node_summary"] == ""
    assert docs["spec"]["mission"]["goal"] == ""
    assert docs["state"]["phase"] == "planning"


def test_create_node_directory_existing_path_raises(tmp_path) -> None:
    node_dir = tmp_path / "test_node"
    create_node_directory(node_dir, empty_task(), empty_briefing(), empty_spec(), default_state())
    with pytest.raises(FileExistsError):
        create_node_directory(node_dir, empty_task(), empty_briefing(), empty_spec(), default_state())


def test_read_spec_compatibility_parses_old_blob_format(tmp_path) -> None:
    (tmp_path / "spec.md").write_text(
        "\n".join(
            [
                "# Spec",
                "",
                "## 1. Mission",
                "- goal: Show catalog",
                "- success_outcome: Catalog page",
                "- implementation_level: working",
                "",
                "## 2. Scope",
                "- must_do:",
                "  - Show catalog",
                "- must_not_do:",
                "  - Do not add checkout",
                "- deferred_work:",
                "  - None yet",
                "",
                "## 3. Constraints",
                "- hard_constraints:",
                "  - Use existing schema",
                "- change_budget: Keep edits local.",
                "- touch_boundaries:",
                "  - frontend/src/features/catalog",
                "- external_dependencies:",
                "  - None",
                "",
                "## 4. Autonomy",
                "- allowed_decisions:",
                "  - Local UI choices",
                "- requires_confirmation:",
                "  - Scope expansion",
                "- default_policy_when_unclear: ask_user",
                "",
                "## 5. Verification",
                "- acceptance_checks:",
                "  - Page loads",
                "- definition_of_done: Catalog works end-to-end.",
                "- evidence_expected:",
                "  - Screenshot",
                "",
                "## 6. Execution Controls",
                "- quality_profile: standard",
                "- tooling_limits:",
                "  - workspace only",
                "- output_expectation: concise progress updates",
                "- conflict_policy: reopen_spec",
                "- missing_decision_policy: reopen_spec",
                "",
                "## 7. Assumptions",
                "- assumptions_in_force:",
                "  - Seeded data OK",
                "",
            ]
        ),
        encoding="utf-8",
    )

    spec = read_spec(tmp_path)

    assert spec["mission"]["goal"] == "Show catalog"
    assert spec["scope"]["must_do"] == ["Show catalog"]
    assert spec["constraints"]["touch_boundaries"] == ["frontend/src/features/catalog"]


def test_read_briefing_compatibility_maps_runtime_phase_into_status(tmp_path) -> None:
    (tmp_path / "briefing.md").write_text(
        "\n".join(
            [
                "# Brief",
                "",
                "## Node Snapshot",
                "- node_summary: Own the scaffold",
                "- why_this_node_exists_now: Baseline handoff",
                "- current_focus: Confirm the spec",
                "",
                "## Active Inherited Context",
                "- active_goals_from_parent:",
                "  - Create the app",
                "- active_constraints_from_parent:",
                "  - None",
                "- active_decisions_in_force:",
                "  - Stay scoped",
                "",
                "## Accepted Upstream Facts",
                "- accepted_outputs:",
                "  - None",
                "- available_artifacts:",
                "  - task.md",
                "- confirmed_dependencies:",
                "  - None",
                "",
                "## Runtime State",
                "- phase: awaiting_brief",
                "- status: ready",
                "- completed_so_far:",
                "  - None",
                "- current_blockers:",
                "  - None",
                "- next_best_action: Confirm the spec",
                "",
                "## Pending Escalations",
                "- open_risks:",
                "  - None",
                "- pending_user_decisions:",
                "  - Confirm the spec",
                "- fallback_direction_if_unanswered: Stay within scope",
                "",
            ]
        ),
        encoding="utf-8",
    )

    brief = read_briefing(tmp_path)

    assert brief["runtime_state"]["status"] == "ready (workflow phase: awaiting_brief)"
