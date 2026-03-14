from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import yaml

from backend.storage.file_utils import atomic_write_text, ensure_dir, load_text

TASK_SECTIONS = ["Title", "Purpose", "Responsibility"]

BRIEF_SCHEMA = (
    (
        "node_snapshot",
        "Node Snapshot",
        (
            ("node_summary", "Node Summary", "scalar"),
            ("why_this_node_exists_now", "Why This Node Exists Now", "scalar"),
            ("current_focus", "Current Focus", "scalar"),
        ),
    ),
    (
        "active_inherited_context",
        "Active Inherited Context",
        (
            ("active_goals_from_parent", "Active Goals From Parent", "list"),
            ("active_constraints_from_parent", "Active Constraints From Parent", "list"),
            ("active_decisions_in_force", "Active Decisions In Force", "list"),
        ),
    ),
    (
        "accepted_upstream_facts",
        "Accepted Upstream Facts",
        (
            ("accepted_outputs", "Accepted Outputs", "list"),
            ("available_artifacts", "Available Artifacts", "list"),
            ("confirmed_dependencies", "Confirmed Dependencies", "list"),
        ),
    ),
    (
        "runtime_state",
        "Runtime State",
        (
            ("status", "Status", "scalar"),
            ("completed_so_far", "Completed So Far", "list"),
            ("current_blockers", "Current Blockers", "list"),
            ("next_best_action", "Next Best Action", "scalar"),
        ),
    ),
    (
        "pending_escalations",
        "Pending Escalations",
        (
            ("open_risks", "Open Risks", "list"),
            ("pending_user_decisions", "Pending User Decisions", "list"),
            (
                "fallback_direction_if_unanswered",
                "Fallback Direction If Unanswered",
                "scalar",
            ),
        ),
    ),
)

SPEC_SCHEMA = (
    (
        "mission",
        "1. Mission",
        (
            ("goal", "Goal", "scalar"),
            ("success_outcome", "Success Outcome", "scalar"),
            ("implementation_level", "Implementation Level", "scalar"),
        ),
    ),
    (
        "scope",
        "2. Scope",
        (
            ("must_do", "Must Do", "list"),
            ("must_not_do", "Must Not Do", "list"),
            ("deferred_work", "Deferred Work", "list"),
        ),
    ),
    (
        "constraints",
        "3. Constraints",
        (
            ("hard_constraints", "Hard Constraints", "list"),
            ("change_budget", "Change Budget", "scalar"),
            ("touch_boundaries", "Touch Boundaries", "list"),
            ("external_dependencies", "External Dependencies", "list"),
        ),
    ),
    (
        "autonomy",
        "4. Autonomy",
        (
            ("allowed_decisions", "Allowed Decisions", "list"),
            ("requires_confirmation", "Requires Confirmation", "list"),
            (
                "default_policy_when_unclear",
                "Default Policy When Unclear",
                "scalar",
            ),
        ),
    ),
    (
        "verification",
        "5. Verification",
        (
            ("acceptance_checks", "Acceptance Checks", "list"),
            ("definition_of_done", "Definition Of Done", "scalar"),
            ("evidence_expected", "Evidence Expected", "list"),
        ),
    ),
    (
        "execution_controls",
        "6. Execution Controls",
        (
            ("quality_profile", "Quality Profile", "scalar"),
            ("tooling_limits", "Tooling Limits", "list"),
            ("output_expectation", "Output Expectation", "scalar"),
            ("conflict_policy", "Conflict Policy", "scalar"),
            ("missing_decision_policy", "Missing Decision Policy", "scalar"),
        ),
    ),
    (
        "assumptions",
        "7. Assumptions",
        (
            ("assumptions_in_force", "Assumptions In Force", "list"),
        ),
    ),
)

BRIEF_SECTIONS = [heading for _, heading, _ in BRIEF_SCHEMA]
SPEC_SECTIONS = [heading for _, heading, _ in SPEC_SCHEMA]

STATE_DEFAULTS: dict[str, Any] = {
    "phase": "planning",
    "task_confirmed": False,
    "briefing_confirmed": False,
    "brief_generation_status": "missing",
    "brief_generation_started_at": "",
    "brief_version": 0,
    "brief_created_at": "",
    "brief_created_from_predecessor_node_id": "",
    "brief_generated_by": "",
    "brief_source_hash": "",
    "brief_source_refs": [],
    "brief_late_upstream_policy": "ignore",
    "spec_initialized": False,
    "spec_generated": False,
    "spec_generation_status": "idle",
    "spec_generation_started_at": "",
    "spec_confirmed": False,
    "active_spec_version": 0,
    "spec_status": "draft",
    "spec_confirmed_at": "",
    "initialized_from_brief_version": 0,
    "spec_content_hash": "",
    "active_plan_version": 0,
    "plan_status": "none",
    "bound_plan_spec_version": 0,
    "bound_plan_brief_version": 0,
    "active_plan_input_version": 0,
    "bound_plan_input_version": 0,
    "bound_turn_id": "",
    "final_plan_item_id": "",
    "structured_result_hash": "",
    "resolved_request_ids": [],
    "spec_update_change_summary": "",
    "spec_update_changed_contract_axes": [],
    "spec_update_recommended_next_step": "",
    "run_status": "idle",
    "pending_plan_questions": [],
    "pending_spec_questions": [],
    "planning_thread_id": "",
    "execution_thread_id": "",
    "ask_thread_id": "",
    "planning_thread_forked_from_node": "",
    "planning_thread_bootstrapped_at": "",
    "chat_session_id": "",
    "last_agent_failure": None,
}

_TOP_FIELD_PATTERN = re.compile(r"^- ([a-z0-9_]+):(.*)$")
_NESTED_BULLET_PATTERN = re.compile(r"^\s+- (.+)$")


def _is_section_heading(line: str) -> bool:
    return line.startswith("## ") and not line.startswith("###")


def _flush_section(
    sections: dict[str, str],
    current_key: str | None,
    current_lines: list[str],
) -> None:
    if current_key is None:
        return
    sections[current_key] = "\n".join(current_lines).strip()


def parse_md_sections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if _is_section_heading(line):
            _flush_section(sections, current_key, current_lines)
            current_key = line[3:].strip()
            if current_key in sections:
                raise ValueError(f"Duplicate markdown section: {current_key}")
            current_lines = []
            continue

        if line.startswith("# ") and not line.startswith("##") and current_key is None:
            continue
        if current_key is None:
            continue
        current_lines.append(line)

    _flush_section(sections, current_key, current_lines)
    return sections


def validate_sections(doc_name: str, sections: dict[str, str], allowed: list[str]) -> None:
    unknown = [heading for heading in sections if heading not in allowed]
    if unknown:
        raise ValueError(f"{doc_name} contains unknown sections: {', '.join(unknown)}")

    missing = [heading for heading in allowed if heading not in sections]
    if missing:
        raise ValueError(f"{doc_name} is missing required sections: {', '.join(missing)}")


def render_md_sections(doc_title: str, sections: dict[str, str]) -> str:
    lines = [f"# {doc_title}", ""]
    for heading, content in sections.items():
        lines.append(f"## {heading}")
        if content:
            lines.extend(content.splitlines())
        lines.append("")
    return "\n".join(lines)


def _parse_subsections(text: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("### "):
            if current_key is not None:
                sections[current_key] = "\n".join(current_lines).strip()
            current_key = line[4:].strip()
            if current_key in sections:
                raise ValueError(f"Duplicate markdown subsection: {current_key}")
            current_lines = []
            continue
        if current_key is None:
            if line.strip():
                raise ValueError("Structured subsection content must start with a ### heading.")
            continue
        current_lines.append(line)

    if current_key is not None:
        sections[current_key] = "\n".join(current_lines).strip()
    return sections


def _normalize_scalar(value: Any) -> str:
    return str(value or "").strip()


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        item = value.strip()
        return [item] if item else []
    if not isinstance(value, list):
        raise ValueError("Expected a list of strings.")
    normalized: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _empty_structured_document(schema: tuple[tuple[str, str, tuple[tuple[str, str, str], ...]], ...]) -> dict[str, Any]:
    document: dict[str, Any] = {}
    for section_key, _, fields in schema:
        document[section_key] = {
            field_key: ([] if field_type == "list" else "")
            for field_key, _, field_type in fields
        }
    return document


def _render_subfield_value(value: Any, field_type: str) -> list[str]:
    if field_type == "list":
        return [f"- {item}" for item in _normalize_list(value)]
    content = _normalize_scalar(value)
    return content.splitlines() if content else []


def _render_structured_sections(
    doc_title: str,
    payload: dict[str, Any],
    schema: tuple[tuple[str, str, tuple[tuple[str, str, str], ...]], ...],
) -> str:
    normalized = _normalize_structured_document(payload, schema)
    lines = [f"# {doc_title}", ""]
    for section_key, section_heading, fields in schema:
        lines.append(f"## {section_heading}")
        lines.append("")
        section_payload = normalized[section_key]
        for field_key, field_heading, field_type in fields:
            lines.append(f"### {field_heading}")
            lines.extend(_render_subfield_value(section_payload[field_key], field_type))
            lines.append("")
    return "\n".join(lines)


def _parse_structured_section(
    content: str,
    fields: tuple[tuple[str, str, str], ...],
) -> dict[str, Any] | None:
    if "### " not in content:
        return None

    subsections = _parse_subsections(content)
    expected_headings = [heading for _, heading, _ in fields]
    unknown = [heading for heading in subsections if heading not in expected_headings]
    if unknown:
        raise ValueError(f"Unknown subsection headings: {', '.join(unknown)}")

    missing = [heading for heading in expected_headings if heading not in subsections]
    if missing:
        raise ValueError(f"Missing subsection headings: {', '.join(missing)}")

    result: dict[str, Any] = {}
    for field_key, field_heading, field_type in fields:
        raw_value = subsections[field_heading]
        result[field_key] = (
            _parse_list_content(raw_value) if field_type == "list" else _normalize_scalar(raw_value)
        )
    return result


def _parse_list_content(content: str) -> list[str]:
    if not content.strip():
        return []
    items: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
            continue
        if not items:
            raise ValueError("List subsection content must use bullet list items.")
        items[-1] = f"{items[-1]}\n{stripped}".strip()
    return items


def _parse_compat_keyed_fields(content: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    current_key: str | None = None
    current_mode: str | None = None
    buffer: list[str] = []

    def flush_current() -> None:
        nonlocal current_key, current_mode, buffer
        if current_key is None:
            return
        if current_mode == "list":
            parsed[current_key] = [item for item in buffer if item.strip()]
        else:
            parsed[current_key] = "\n".join(buffer).strip()
        current_key = None
        current_mode = None
        buffer = []

    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if current_key is not None and current_mode == "scalar":
                buffer.append("")
            continue

        top_match = _TOP_FIELD_PATTERN.match(line)
        if top_match:
            flush_current()
            current_key = top_match.group(1)
            inline_value = top_match.group(2).strip()
            if inline_value:
                current_mode = "scalar"
                buffer = [inline_value]
            else:
                current_mode = "pending"
                buffer = []
            continue

        nested_match = _NESTED_BULLET_PATTERN.match(line)
        if nested_match and current_key is not None:
            item = nested_match.group(1).strip()
            if current_mode in {"pending", "list"}:
                current_mode = "list"
                buffer.append(item)
                continue

        if current_key is None:
            raise ValueError("Compatibility parse failed: content must use '- key:' entries.")

        stripped = line.strip()
        if current_mode == "list":
            if not buffer:
                raise ValueError("Compatibility parse failed: malformed list entry.")
            buffer[-1] = f"{buffer[-1]}\n{stripped}".strip()
            continue

        if current_mode == "pending":
            current_mode = "scalar"
        buffer.append(stripped)

    flush_current()
    return parsed


def _parse_compat_section(
    doc_name: str,
    section_key: str,
    content: str,
    fields: tuple[tuple[str, str, str], ...],
) -> dict[str, Any]:
    if not content.strip():
        return {
            field_key: ([] if field_type == "list" else "")
            for field_key, _, field_type in fields
        }

    parsed = _parse_compat_keyed_fields(content)
    if doc_name == "briefing.md" and section_key == "runtime_state" and "phase" in parsed:
        phase_value = _normalize_scalar(parsed.pop("phase"))
        current_status = _normalize_scalar(parsed.get("status"))
        if phase_value:
            parsed["status"] = (
                f"{current_status} (workflow phase: {phase_value})"
                if current_status
                else phase_value
            )
    allowed = {field_key: field_type for field_key, _, field_type in fields}
    unknown = [field_key for field_key in parsed if field_key not in allowed]
    if unknown:
        raise ValueError(
            f"Compatibility parse failed for {doc_name}: unknown subfields {', '.join(unknown)}"
        )

    result: dict[str, Any] = {}
    for field_key, _, field_type in fields:
        raw_value = parsed.get(field_key)
        if field_type == "list":
            result[field_key] = _normalize_list(raw_value)
        else:
            result[field_key] = _normalize_scalar(raw_value)
    return result


def _normalize_structured_document(
    payload: dict[str, Any],
    schema: tuple[tuple[str, str, tuple[tuple[str, str, str], ...]], ...],
) -> dict[str, Any]:
    normalized = _empty_structured_document(schema)
    if not isinstance(payload, dict):
        return normalized

    field_lookup = {section_key: fields for section_key, _, fields in schema}
    for section_key, fields in field_lookup.items():
        raw_section = payload.get(section_key, {})
        if isinstance(raw_section, str):
            normalized[section_key] = _parse_compat_section(section_key, section_key, raw_section, fields)
            continue
        if raw_section is None:
            continue
        if not isinstance(raw_section, dict):
            raise ValueError(f"{section_key} must be an object.")
        next_section = dict(normalized[section_key])
        allowed_fields = {field_key: field_type for field_key, _, field_type in fields}
        unknown = [field_key for field_key in raw_section if field_key not in allowed_fields]
        if unknown:
            raise ValueError(
                f"{section_key} contains unknown fields: {', '.join(unknown)}"
            )
        for field_key, field_type in allowed_fields.items():
            if field_key not in raw_section:
                continue
            next_section[field_key] = (
                _normalize_list(raw_section[field_key])
                if field_type == "list"
                else _normalize_scalar(raw_section[field_key])
            )
        normalized[section_key] = next_section
    return normalized


def _write_migration_backup(path: Path, content: str) -> None:
    backup_path = path.with_name(f"{path.name}.v1.bak")
    if backup_path.exists():
        return
    atomic_write_text(backup_path, content)


def _read_structured_document(
    path: Path,
    *,
    doc_name: str,
    doc_title: str,
    schema: tuple[tuple[str, str, tuple[tuple[str, str, str], ...]], ...],
) -> dict[str, Any]:
    text = load_text(path)
    sections = parse_md_sections(text)
    validate_sections(doc_name, sections, [heading for _, heading, _ in schema])

    result = _empty_structured_document(schema)
    try:
        for section_key, section_heading, fields in schema:
            content = sections.get(section_heading, "")
            structured = _parse_structured_section(content, fields)
            if structured is not None:
                result[section_key] = structured
            else:
                result[section_key] = _parse_compat_section(doc_name, section_key, content, fields)
    except ValueError:
        _write_migration_backup(path, text)
        raise
    return result


def read_task(node_dir: Path) -> dict[str, str]:
    sections = parse_md_sections(load_text(node_dir / "task.md"))
    validate_sections("task.md", sections, TASK_SECTIONS)
    return {
        "title": sections.get("Title", ""),
        "purpose": sections.get("Purpose", ""),
        "responsibility": sections.get("Responsibility", ""),
    }


def write_task(node_dir: Path, task: dict[str, str]) -> None:
    content = render_md_sections(
        "Task",
        {
            "Title": task.get("title", ""),
            "Purpose": task.get("purpose", ""),
            "Responsibility": task.get("responsibility", ""),
        },
    )
    atomic_write_text(node_dir / "task.md", content)


def read_brief(node_dir: Path) -> dict[str, Any]:
    return _read_structured_document(
        node_dir / "briefing.md",
        doc_name="briefing.md",
        doc_title="Brief",
        schema=BRIEF_SCHEMA,
    )


def write_brief(node_dir: Path, brief: dict[str, Any]) -> None:
    content = _render_structured_sections("Brief", brief, BRIEF_SCHEMA)
    atomic_write_text(node_dir / "briefing.md", content)


def read_spec(node_dir: Path) -> dict[str, Any]:
    return _read_structured_document(
        node_dir / "spec.md",
        doc_name="spec.md",
        doc_title="Spec",
        schema=SPEC_SCHEMA,
    )


def write_spec(node_dir: Path, spec: dict[str, Any]) -> None:
    content = _render_structured_sections("Spec", spec, SPEC_SCHEMA)
    atomic_write_text(node_dir / "spec.md", content)


def read_plan(node_dir: Path) -> dict[str, str]:
    plan_path = node_dir / "plan.md"
    if not plan_path.exists():
        return {"content": ""}
    return {"content": load_text(plan_path)}


def write_plan(node_dir: Path, plan: dict[str, str]) -> None:
    atomic_write_text(node_dir / "plan.md", str(plan.get("content") or ""))


def read_state(node_dir: Path) -> dict[str, Any]:
    text = load_text(node_dir / "state.yaml")
    if not text.strip():
        raise ValueError("state.yaml is empty")

    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError("state.yaml is malformed") from exc

    if not isinstance(parsed, dict):
        raise ValueError("state.yaml must contain a mapping")

    result = dict(STATE_DEFAULTS)
    result.update(parsed)
    if str(result.get("plan_status") or "") == "questioning":
        result["plan_status"] = "waiting_on_input"
    if not result.get("pending_plan_questions") and result.get("pending_spec_questions"):
        result["pending_plan_questions"] = copy.deepcopy(result.get("pending_spec_questions", []))
    if not result.get("pending_spec_questions") and result.get("pending_plan_questions"):
        result["pending_spec_questions"] = copy.deepcopy(result.get("pending_plan_questions", []))
    return result


def write_state(node_dir: Path, state: dict[str, Any]) -> None:
    ordered = dict(STATE_DEFAULTS)
    if "pending_plan_questions" in state and "pending_spec_questions" not in state:
        state = dict(state)
        state["pending_spec_questions"] = copy.deepcopy(state["pending_plan_questions"])
    elif "pending_spec_questions" in state and "pending_plan_questions" not in state:
        state = dict(state)
        state["pending_plan_questions"] = copy.deepcopy(state["pending_spec_questions"])
    for key in STATE_DEFAULTS:
        if key in state:
            ordered[key] = state[key]
    content = yaml.safe_dump(
        ordered,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    atomic_write_text(node_dir / "state.yaml", content)


def create_node_directory(
    node_dir: Path,
    task: dict[str, str],
    brief: dict[str, Any],
    spec: dict[str, Any],
    state: dict[str, Any],
) -> None:
    if node_dir.exists():
        raise FileExistsError(f"Node directory already exists: {node_dir}")

    ensure_dir(node_dir)
    write_task(node_dir, task)
    write_brief(node_dir, brief)
    write_spec(node_dir, spec)
    write_plan(node_dir, {"content": ""})
    write_state(node_dir, state)


def load_all(node_dir: Path) -> dict[str, Any]:
    brief = read_brief(node_dir)
    return {
        "task": read_task(node_dir),
        "brief": brief,
        "briefing": copy.deepcopy(brief),
        "spec": read_spec(node_dir),
        "plan": read_plan(node_dir),
        "state": read_state(node_dir),
    }


def empty_task() -> dict[str, str]:
    return {"title": "", "purpose": "", "responsibility": ""}


def empty_brief() -> dict[str, Any]:
    return _empty_structured_document(BRIEF_SCHEMA)


def empty_spec() -> dict[str, Any]:
    return _empty_structured_document(SPEC_SCHEMA)


def default_state() -> dict[str, Any]:
    return dict(STATE_DEFAULTS)


def read_briefing(node_dir: Path) -> dict[str, Any]:
    return read_brief(node_dir)


def write_briefing(node_dir: Path, briefing: dict[str, Any]) -> None:
    write_brief(node_dir, briefing)


def empty_briefing() -> dict[str, Any]:
    return empty_brief()
