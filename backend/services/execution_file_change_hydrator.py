from __future__ import annotations

import copy
import logging
import re
from pathlib import Path
from typing import Any, Protocol

from backend.conversation.projector.thread_event_projector import patch_item, upsert_item
from backend.storage.file_utils import iso_now

_COUNTER_UPSTREAM_FULL_DIFF = "upstream_filechange_full_diff"
_COUNTER_HYDRATED_FROM_GIT = "hydrated_from_git_diff"
_COUNTER_SYNTHETIC_FROM_COMMAND_ONLY = "synthetic_filechange_from_command_only"
_COUNTER_SKIPPED_NO_DIFF = "skipped_no_diff"
_COUNTER_FILTERED_PLANNINGTREE = "filtered_planningtree_changes"
_COUNTER_KEYS = (
    _COUNTER_UPSTREAM_FULL_DIFF,
    _COUNTER_HYDRATED_FROM_GIT,
    _COUNTER_SYNTHETIC_FROM_COMMAND_ONLY,
    _COUNTER_SKIPPED_NO_DIFF,
    _COUNTER_FILTERED_PLANNINGTREE,
)


class ExecutionFileChangeDiffSource(Protocol):
    mode: str

    def get_diff_for_paths(self, paths: list[str]) -> str:
        ...

    def get_full_diff(self) -> str:
        ...


class ExecutionFileChangeHydrator:
    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def hydrate_turn_snapshot(
        self,
        *,
        snapshot: dict[str, Any],
        turn_id: str,
        diff_source: ExecutionFileChangeDiffSource,
        hydrated_by: str,
        project_id: str,
        node_id: str,
        refresh_synthetic_from_full_diff: bool = False,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, int]]:
        counters = self._new_counters()
        updated_snapshot = copy.deepcopy(snapshot)
        pending_events: list[dict[str, Any]] = []
        turn_file_change_items: list[dict[str, Any]] = []
        explicit_empty_changes = False
        hydrated_existing_file_change = False
        synthetic_item_id: str | None = None

        for item in list(updated_snapshot.get("items", [])):
            if not isinstance(item, dict):
                continue
            if str(item.get("kind") or "") != "tool":
                continue
            if str(item.get("turnId") or "") != turn_id:
                continue
            if str(item.get("toolType") or "") != "fileChange":
                continue

            if self._file_change_item_has_planningtree_paths(item):
                sanitized_changes = self._extract_file_change_changes(item, counters=counters)
                sanitized_item = copy.deepcopy(item)
                sanitized_item["changes"] = sanitized_changes
                sanitized_item["outputFiles"] = self._output_files_from_changes(sanitized_changes)
                sanitized_item["outputText"] = self._output_text_from_changes(sanitized_changes)
                sanitized_item["updatedAt"] = iso_now()
                updated_snapshot, events = upsert_item(updated_snapshot, sanitized_item)
                pending_events.extend(events)
                item = sanitized_item

            if self._is_synthetic_file_change_item(item):
                candidate_item_id = str(item.get("id") or "").strip()
                if candidate_item_id:
                    synthetic_item_id = candidate_item_id

            turn_file_change_items.append(item)
            if refresh_synthetic_from_full_diff and self._is_synthetic_file_change_item(item):
                continue
            if isinstance(item.get("changes"), list) and len(item.get("changes") or []) == 0:
                explicit_empty_changes = True
                continue

            output_text = str(item.get("outputText") or "")
            arguments_text = str(item.get("argumentsText") or "")
            if self._looks_like_structured_diff(output_text) or self._looks_like_structured_diff(arguments_text):
                hydrated_existing_file_change = True
                self._inc(counters, _COUNTER_UPSTREAM_FULL_DIFF)
                continue

            baseline_changes = self._extract_file_change_changes(item, counters=counters)
            if not baseline_changes:
                self._inc(counters, _COUNTER_SKIPPED_NO_DIFF)
                continue
            if any(str(change.get("diff") or "").strip() for change in baseline_changes):
                hydrated_existing_file_change = True
                self._inc(counters, _COUNTER_UPSTREAM_FULL_DIFF)
                continue

            paths = [str(change.get("path") or "").strip() for change in baseline_changes if str(change.get("path") or "").strip()]
            diff_text = str(diff_source.get_diff_for_paths(paths) or "")
            if not diff_text.strip() and paths:
                diff_text = str(diff_source.get_full_diff() or "")
            trimmed_diff = diff_text.strip()
            if not trimmed_diff:
                self._inc(counters, _COUNTER_SKIPPED_NO_DIFF)
                continue

            blocks = self._parse_unified_diff_blocks(trimmed_diff)
            hydrated_changes: list[dict[str, Any]] = []
            did_hydrate = False
            for index, change in enumerate(baseline_changes):
                block = self._resolve_diff_block_for_path(
                    blocks,
                    path=str(change.get("path") or ""),
                    file_index=index,
                )
                diff_value = str(block.get("text") or "").strip() if isinstance(block, dict) else ""
                next_change = copy.deepcopy(change)
                next_change["diff"] = diff_value or None
                hydrated_changes.append(next_change)
                if diff_value:
                    did_hydrate = True

            if not did_hydrate:
                self._inc(counters, _COUNTER_SKIPPED_NO_DIFF)
                continue

            updated_snapshot, events = patch_item(
                updated_snapshot,
                str(item.get("id") or ""),
                {
                    "kind": "tool",
                    "changesReplace": hydrated_changes,
                    "outputFilesReplace": self._output_files_from_changes(hydrated_changes),
                    "updatedAt": iso_now(),
                },
            )
            pending_events.extend(events)
            hydrated_existing_file_change = True
            self._inc(counters, _COUNTER_HYDRATED_FROM_GIT)

        should_refresh_existing_synthetic = (
            refresh_synthetic_from_full_diff
            and bool(synthetic_item_id)
            and not explicit_empty_changes
            and not hydrated_existing_file_change
        )
        should_hydrate_from_command_only = should_refresh_existing_synthetic or not turn_file_change_items or (
            turn_file_change_items and not explicit_empty_changes and not hydrated_existing_file_change
        )
        if should_hydrate_from_command_only:
            full_diff_text = str(diff_source.get_full_diff() or "")
            trimmed_full_diff = full_diff_text.strip()
            if trimmed_full_diff:
                blocks = self._parse_unified_diff_blocks(trimmed_full_diff)
                synthetic_changes = self._changes_from_diff_blocks(blocks, counters=counters)
                if synthetic_changes:
                    if turn_file_change_items:
                        target_item_id = (
                            str(synthetic_item_id or "").strip()
                            if should_refresh_existing_synthetic
                            else str(turn_file_change_items[0].get("id") or "")
                        )
                        if target_item_id:
                            updated_snapshot, events = patch_item(
                                updated_snapshot,
                                target_item_id,
                                {
                                    "kind": "tool",
                                    "changesReplace": synthetic_changes,
                                    "outputFilesReplace": self._output_files_from_changes(synthetic_changes),
                                    "updatedAt": iso_now(),
                                },
                            )
                            pending_events.extend(events)
                            self._inc(counters, _COUNTER_SYNTHETIC_FROM_COMMAND_ONLY)
                    else:
                        sequence = max(
                            (
                                int(existing.get("sequence") or 0)
                                for existing in updated_snapshot.get("items", [])
                                if isinstance(existing, dict)
                            ),
                            default=0,
                        ) + 1
                        synthetic_item_id = f"turn:{turn_id}:hydrated-file-change"
                        synthetic_item = {
                            "id": synthetic_item_id,
                            "kind": "tool",
                            "threadId": str(updated_snapshot.get("threadId") or ""),
                            "turnId": turn_id,
                            "sequence": sequence,
                            "createdAt": iso_now(),
                            "updatedAt": iso_now(),
                            "status": "completed",
                            "source": "backend",
                            "tone": "neutral",
                            "metadata": {
                                "hydratedBy": hydrated_by,
                                "synthetic": True,
                                "mode": str(getattr(diff_source, "mode", "") or ""),
                            },
                            "toolType": "fileChange",
                            "title": "File changes",
                            "toolName": "git-diff-hydrator",
                            "callId": None,
                            "argumentsText": None,
                            "outputText": self._output_text_from_changes(synthetic_changes),
                            "outputFiles": self._output_files_from_changes(synthetic_changes),
                            "changes": synthetic_changes,
                            "exitCode": None,
                        }
                        updated_snapshot, events = upsert_item(updated_snapshot, synthetic_item)
                        pending_events.extend(events)
                        self._inc(counters, _COUNTER_SYNTHETIC_FROM_COMMAND_ONLY)
                else:
                    self._inc(counters, _COUNTER_SKIPPED_NO_DIFF)
            else:
                self._inc(counters, _COUNTER_SKIPPED_NO_DIFF)

        self._emit_counter_logs(
            counters=counters,
            mode=str(getattr(diff_source, "mode", "") or ""),
            project_id=project_id,
            node_id=node_id,
            turn_id=turn_id,
        )
        return updated_snapshot, pending_events, counters

    @staticmethod
    def _new_counters() -> dict[str, int]:
        return {key: 0 for key in _COUNTER_KEYS}

    @staticmethod
    def _inc(counters: dict[str, int], key: str, amount: int = 1) -> None:
        counters[key] = int(counters.get(key, 0)) + int(amount)

    def _emit_counter_logs(
        self,
        *,
        counters: dict[str, int],
        mode: str,
        project_id: str,
        node_id: str,
        turn_id: str,
    ) -> None:
        for key in _COUNTER_KEYS:
            count = int(counters.get(key, 0))
            if count <= 0:
                continue
            self._logger.info(
                "execution_file_change_hydrator counter=%s count=%s mode=%s project_id=%s node_id=%s turn_id=%s",
                key,
                count,
                mode,
                project_id,
                node_id,
                turn_id,
            )

    @staticmethod
    def _looks_like_structured_diff(text: str | None) -> bool:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            return False
        return (
            "diff --git " in normalized
            or "*** Begin Patch" in normalized
            or "\n@@ " in f"\n{normalized}"
            or "\n+++ " in f"\n{normalized}"
            or "\n--- " in f"\n{normalized}"
        )

    @staticmethod
    def _normalize_path_for_diff_match(path: str | None) -> str:
        candidate = str(path or "").replace("\\", "/").strip()
        if not candidate:
            return ""
        if len(candidate) >= 2 and candidate[1] == ":":
            candidate = candidate[2:]
        candidate = candidate.lstrip("/")
        candidate = re.sub(r"^\./+", "", candidate)
        return candidate.lower()

    @classmethod
    def _is_planningtree_path(cls, path: str | None) -> bool:
        normalized = cls._normalize_path_for_diff_match(path)
        return normalized == ".planningtree" or normalized.startswith(".planningtree/")

    @staticmethod
    def _strip_git_ab_prefix(path: str) -> str:
        candidate = str(path or "").strip().replace("\\", "/")
        if candidate.startswith(("a/", "b/")) and len(candidate) > 2:
            return candidate[2:]
        return candidate

    @classmethod
    def _extract_paths_from_diff_git_header(cls, line: str) -> list[str]:
        payload = line[len("diff --git ") :].strip()
        if not payload:
            return []
        paths: list[str] = []
        rest = payload
        while rest:
            if rest.startswith('"'):
                end = rest.find('"', 1)
                if end < 0:
                    break
                token = rest[1:end]
                rest = rest[end + 1 :].lstrip()
            else:
                space = rest.find(" ")
                token = rest if space < 0 else rest[:space]
                rest = "" if space < 0 else rest[space + 1 :].lstrip()
            normalized = cls._strip_git_ab_prefix(token)
            if normalized:
                paths.append(normalized)
        return paths

    @classmethod
    def _parse_unified_diff_blocks(cls, diff_text: str) -> list[dict[str, Any]]:
        normalized = str(diff_text or "").replace("\r\n", "\n").replace("\r", "\n")
        if not normalized.strip():
            return []
        lines = normalized.split("\n")
        starts: list[tuple[int, list[str]]] = []
        for index, line in enumerate(lines):
            if line.startswith("diff --git "):
                paths = cls._extract_paths_from_diff_git_header(line)
                starts.append((index, paths))
        if not starts:
            return [{"paths": [], "text": normalized.strip()}]
        blocks: list[dict[str, Any]] = []
        for idx, (start, paths) in enumerate(starts):
            end = starts[idx + 1][0] if idx + 1 < len(starts) else len(lines)
            block_text = "\n".join(lines[start:end]).strip()
            if not block_text:
                continue
            blocks.append({"paths": paths, "text": block_text})
        return blocks

    @staticmethod
    def _normalize_change_kind(value: Any, *, fallback: str = "modify") -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"add", "create", "created", "new"}:
            return "add"
        if normalized in {"delete", "deleted", "remove", "removed"}:
            return "delete"
        if normalized in {"modify", "modified", "update", "updated", "change", "changed"}:
            return "modify"
        return fallback

    @staticmethod
    def _change_type_to_kind(value: Any, *, fallback: str = "modify") -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"created", "create", "add"}:
            return "add"
        if normalized in {"deleted", "delete", "remove", "removed"}:
            return "delete"
        if normalized in {"updated", "update", "modify", "modified", "change", "changed"}:
            return "modify"
        return fallback

    @staticmethod
    def _change_kind_to_change_type(kind: str) -> str:
        if kind == "add":
            return "created"
        if kind == "delete":
            return "deleted"
        return "updated"

    @classmethod
    def _extract_file_change_changes(
        cls,
        item: dict[str, Any],
        *,
        counters: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        raw_changes = item.get("changes") if isinstance(item.get("changes"), list) else None
        rows = (
            raw_changes
            if raw_changes is not None
            else item.get("outputFiles")
            if isinstance(item.get("outputFiles"), list)
            else []
        )
        extracted: list[dict[str, Any]] = []
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path") or "").strip()
            if not path:
                continue
            if cls._is_planningtree_path(path):
                if counters is not None:
                    cls._inc(counters, _COUNTER_FILTERED_PLANNINGTREE)
                continue
            kind = cls._normalize_change_kind(
                raw.get("kind"),
                fallback=cls._change_type_to_kind(raw.get("changeType"), fallback="modify"),
            )
            diff_value = raw.get("diff")
            if not isinstance(diff_value, str):
                diff_value = raw.get("patchText")
            if not isinstance(diff_value, str):
                diff_value = raw.get("patch_text")
            diff_text = str(diff_value or "").strip() or None
            summary_value = raw.get("summary")
            summary = str(summary_value).strip() if isinstance(summary_value, str) and str(summary_value).strip() else None
            extracted.append(
                {
                    "path": path,
                    "kind": kind,
                    "diff": diff_text,
                    "summary": summary,
                }
            )
        return extracted

    @classmethod
    def _output_files_from_changes(cls, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        for change in changes:
            path = str(change.get("path") or "").strip()
            if not path:
                continue
            if cls._is_planningtree_path(path):
                continue
            kind = cls._normalize_change_kind(change.get("kind"), fallback="modify")
            file_entry: dict[str, Any] = {
                "path": path,
                "changeType": cls._change_kind_to_change_type(kind),
                "summary": str(change.get("summary")).strip() if isinstance(change.get("summary"), str) and str(change.get("summary")).strip() else None,
                "kind": kind,
            }
            diff_text = str(change.get("diff") or "").strip()
            if diff_text:
                file_entry["diff"] = diff_text
            files.append(file_entry)
        return files

    @classmethod
    def _score_paths_for_match(cls, candidate_paths: list[str], target_path: str) -> int:
        if not target_path:
            return 0
        target_base = Path(target_path).name.lower()
        best = 0
        for candidate in candidate_paths:
            normalized = cls._normalize_path_for_diff_match(candidate)
            if not normalized:
                continue
            if normalized == target_path:
                return 10000 + len(normalized)
            if target_path.endswith(f"/{normalized}") or normalized.endswith(f"/{target_path}"):
                best = max(best, 5000 + min(len(normalized), len(target_path)))
                continue
            if normalized.endswith(target_base) and target_base:
                best = max(best, 500 + len(normalized))
        return best

    @classmethod
    def _resolve_diff_block_for_path(
        cls,
        blocks: list[dict[str, Any]],
        *,
        path: str,
        file_index: int,
    ) -> dict[str, Any] | None:
        normalized_target = cls._normalize_path_for_diff_match(path)
        best_index = -1
        best_score = 0
        for idx, block in enumerate(blocks):
            block_paths = block.get("paths")
            if not isinstance(block_paths, list):
                continue
            score = cls._score_paths_for_match(block_paths, normalized_target)
            if score > best_score:
                best_score = score
                best_index = idx
        if best_index >= 0 and best_score >= 500:
            return blocks[best_index]
        if 0 <= file_index < len(blocks):
            return blocks[file_index]
        if len(blocks) == 1:
            return blocks[0]
        return None

    @classmethod
    def _primary_path_from_block_paths(cls, paths: list[str] | None) -> str:
        if not isinstance(paths, list):
            return ""
        for candidate in reversed(paths):
            normalized = cls._normalize_path_for_diff_match(candidate)
            if normalized and normalized != "dev/null":
                return str(candidate)
        for candidate in reversed(paths):
            raw = str(candidate or "").strip()
            if raw:
                return raw
        return ""

    @staticmethod
    def _change_kind_from_diff_block_text(text: str) -> str:
        normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
        if (
            re.search(r"(?m)^new file mode\b", normalized)
            or re.search(r"(?m)^--- /dev/null$", normalized)
        ):
            return "add"
        if (
            re.search(r"(?m)^deleted file mode\b", normalized)
            or re.search(r"(?m)^\+\+\+ /dev/null$", normalized)
        ):
            return "delete"
        return "modify"

    @classmethod
    def _changes_from_diff_blocks(
        cls,
        blocks: list[dict[str, Any]],
        *,
        counters: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        if not blocks:
            return []
        changes: list[dict[str, Any]] = []
        seen = set()
        for block in blocks:
            block_paths = block.get("paths")
            path = cls._primary_path_from_block_paths(block_paths if isinstance(block_paths, list) else None)
            normalized_path = cls._normalize_path_for_diff_match(path)
            if not normalized_path or normalized_path == "dev/null" or normalized_path in seen:
                continue
            if cls._is_planningtree_path(path):
                if counters is not None:
                    cls._inc(counters, _COUNTER_FILTERED_PLANNINGTREE)
                continue
            text = str(block.get("text") or "").strip()
            changes.append(
                {
                    "path": path,
                    "kind": cls._change_kind_from_diff_block_text(text),
                    "diff": text or None,
                    "summary": "Hydrated from git diff",
                }
            )
            seen.add(normalized_path)
        return changes

    @classmethod
    def _file_change_item_has_planningtree_paths(cls, item: dict[str, Any]) -> bool:
        rows: list[Any] = []
        raw_changes = item.get("changes")
        raw_output_files = item.get("outputFiles")
        if isinstance(raw_changes, list):
            rows.extend(raw_changes)
        if isinstance(raw_output_files, list):
            rows.extend(raw_output_files)
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            path = str(raw.get("path") or "").strip()
            if cls._is_planningtree_path(path):
                return True
        return False

    @staticmethod
    def _is_synthetic_file_change_item(item: dict[str, Any]) -> bool:
        metadata = item.get("metadata")
        if not isinstance(metadata, dict):
            return False
        return bool(metadata.get("synthetic"))

    @staticmethod
    def _output_text_from_changes(changes: list[dict[str, Any]]) -> str:
        return "\n\n".join(
            str(change.get("diff") or "").strip()
            for change in changes
            if str(change.get("diff") or "").strip()
        )
