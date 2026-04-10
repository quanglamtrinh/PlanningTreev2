from __future__ import annotations

from typing import Any

from backend.conversation.domain.types_v3 import (
    PendingUserInputRequestV3,
    ThreadSnapshotV3,
    copy_snapshot_v3,
)
from backend.errors.app_errors import InvalidRequest
from backend.storage.file_utils import iso_now


class RequestLedgerServiceV3:
    def upsert_requested(
        self,
        snapshot: ThreadSnapshotV3,
        *,
        request_id: str,
        item_id: str,
        thread_id: str,
        turn_id: str | None,
    ) -> ThreadSnapshotV3:
        updated = copy_snapshot_v3(snapshot)
        pending = self._find_pending(updated, request_id)
        if pending is None:
            updated["uiSignals"]["activeUserInputRequests"].append(
                PendingUserInputRequestV3(
                    requestId=request_id,
                    itemId=item_id,
                    threadId=thread_id,
                    turnId=turn_id,
                    status="requested",
                    createdAt=iso_now(),
                    submittedAt=None,
                    resolvedAt=None,
                    answers=[],
                )
            )
            return updated
        pending["itemId"] = item_id
        pending["threadId"] = thread_id
        pending["turnId"] = turn_id
        pending["status"] = "requested"
        return updated

    def submit_answers(
        self,
        snapshot: ThreadSnapshotV3,
        *,
        request_id: str,
        answers: list[dict[str, Any]],
    ) -> ThreadSnapshotV3:
        updated = copy_snapshot_v3(snapshot)
        pending = self._find_pending(updated, request_id)
        if pending is None:
            raise InvalidRequest(f"Unknown user-input request {request_id!r}.")
        pending["answers"] = list(answers)
        pending["submittedAt"] = iso_now()
        pending["status"] = "answer_submitted"
        return updated

    def mark_answered(
        self,
        snapshot: ThreadSnapshotV3,
        *,
        request_id: str,
    ) -> ThreadSnapshotV3:
        updated = copy_snapshot_v3(snapshot)
        pending = self._find_pending(updated, request_id)
        if pending is None:
            return updated
        pending["status"] = "answered"
        pending["resolvedAt"] = iso_now()
        return updated

    def mark_stale_missing_runtime_requests(
        self,
        snapshot: ThreadSnapshotV3,
        *,
        runtime_request_exists: Any,
    ) -> tuple[ThreadSnapshotV3, bool]:
        updated = copy_snapshot_v3(snapshot)
        changed = False
        for pending in updated.get("uiSignals", {}).get("activeUserInputRequests", []):
            status = str(pending.get("status") or "").strip()
            if status not in {"requested", "answer_submitted"}:
                continue
            request_id = str(pending.get("requestId") or "").strip()
            if not request_id:
                continue
            if runtime_request_exists(request_id):
                continue
            pending["status"] = "stale"
            pending["resolvedAt"] = iso_now()
            changed = True
        return updated, changed

    @staticmethod
    def _find_pending(snapshot: ThreadSnapshotV3, request_id: str) -> PendingUserInputRequestV3 | None:
        for pending in snapshot.get("uiSignals", {}).get("activeUserInputRequests", []):
            if pending.get("requestId") == request_id:
                return pending
        return None

