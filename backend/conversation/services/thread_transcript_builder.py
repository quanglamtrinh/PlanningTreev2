from __future__ import annotations

from backend.conversation.domain.types import ThreadSnapshotV2


class ThreadTranscriptBuilder:
    def build_plain_text(self, snapshot: ThreadSnapshotV2) -> str:
        lines: list[str] = []
        for item in snapshot.get("items", []):
            kind = str(item.get("kind") or "").strip()
            if kind == "message":
                role = str(item.get("role") or "").strip()
                text = str(item.get("text") or "")
                lines.append(f"{role}: {text}")
            elif kind == "reasoning":
                lines.append(str(item.get("summaryText") or ""))
            elif kind == "plan":
                lines.append(str(item.get("text") or ""))
            elif kind == "tool":
                lines.append(str(item.get("outputText") or ""))
        return "\n".join(line for line in lines if line)
