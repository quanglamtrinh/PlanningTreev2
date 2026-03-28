from __future__ import annotations

from typing import Any

from backend.conversation.storage.thread_snapshot_store_v2 import ThreadSnapshotStoreV2
from backend.conversation.domain.types import ThreadSnapshotV2
from backend.storage.storage import Storage


class ThreadTranscriptBuilder:
    def __init__(
        self,
        storage: Storage,
        snapshot_store: ThreadSnapshotStoreV2,
    ) -> None:
        self._storage = storage
        self._snapshot_store = snapshot_store

    def build_prompt_messages(
        self,
        project_id: str,
        node_id: str,
        thread_role: str,
    ) -> list[dict[str, str]]:
        if thread_role == "ask_planning":
            session = self._storage.chat_state_store.read_session(
                project_id,
                node_id,
                thread_role=thread_role,
            )
            return self._normalize_legacy_messages(session.get("messages", []))

        snapshot = self._snapshot_store.read_snapshot(project_id, node_id, thread_role)
        return self._prompt_messages_from_snapshot(snapshot)

    def build_plain_text(self, snapshot: ThreadSnapshotV2) -> str:
        messages = self._prompt_messages_from_snapshot(snapshot)
        return "\n".join(
            f"{message['role']}: {message['content']}"
            for message in messages
            if message.get("role") and message.get("content")
        )

    @staticmethod
    def _normalize_legacy_messages(raw_messages: list[dict[str, Any]] | Any) -> list[dict[str, str]]:
        if not isinstance(raw_messages, list):
            return []
        messages: list[dict[str, str]] = []
        for raw in raw_messages:
            if not isinstance(raw, dict):
                continue
            role = str(raw.get("role") or "").strip()
            content = str(raw.get("content") or "").strip()
            if not role or not content:
                continue
            messages.append({"role": role, "content": content})
        return messages

    def _prompt_messages_from_snapshot(self, snapshot: ThreadSnapshotV2) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for item in snapshot.get("items", []):
            kind = str(item.get("kind") or "").strip()
            if kind == "message":
                role = str(item.get("role") or "").strip()
                text = str(item.get("text") or "")
                if role and text.strip():
                    messages.append({"role": role, "content": text})
            elif kind == "reasoning":
                summary = str(item.get("summaryText") or "").strip()
                if summary:
                    messages.append({"role": "assistant", "content": summary})
            elif kind == "plan":
                text = str(item.get("text") or "").strip()
                if text:
                    messages.append({"role": "assistant", "content": text})
            elif kind == "tool":
                output_text = str(item.get("outputText") or "").strip()
                if output_text:
                    messages.append({"role": "system", "content": output_text})
                    continue
                output_files = item.get("outputFiles") if isinstance(item, dict) else []
                if isinstance(output_files, list) and output_files:
                    for output_file in output_files:
                        if not isinstance(output_file, dict):
                            continue
                        path = str(output_file.get("path") or "").strip()
                        change_type = str(output_file.get("changeType") or "").strip()
                        summary = str(output_file.get("summary") or "").strip()
                        if not path:
                            continue
                        content = f"{change_type or 'updated'} {path}"
                        if summary:
                            content = f"{content}: {summary}"
                        messages.append({"role": "system", "content": content})
            elif kind == "status":
                label = str(item.get("label") or "").strip()
                detail = str(item.get("detail") or "").strip()
                content = label if not detail else f"{label}: {detail}"
                if content.strip():
                    messages.append({"role": "system", "content": content})
            elif kind == "error":
                message = str(item.get("message") or "").strip()
                if message:
                    messages.append({"role": "system", "content": message})
            elif kind == "userInput":
                answers = item.get("answers") if isinstance(item, dict) else []
                if not isinstance(answers, list) or not answers:
                    continue
                answer_lines: list[str] = []
                for answer in answers:
                    if not isinstance(answer, dict):
                        continue
                    question_id = str(answer.get("questionId") or "").strip()
                    value = str(answer.get("value") or "").strip()
                    if not value:
                        continue
                    answer_lines.append(f"{question_id}: {value}" if question_id else value)
                if answer_lines:
                    messages.append({"role": "user", "content": "\n".join(answer_lines)})
        return messages
