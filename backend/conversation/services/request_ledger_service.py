from __future__ import annotations

from typing import Any

from backend.conversation.domain.types import PendingUserInputRequest, ThreadSnapshotV2, copy_snapshot
from backend.errors.app_errors import InvalidRequest
from backend.storage.file_utils import iso_now


class RequestLedgerService:
    def upsert_requested(
        self,
        snapshot: ThreadSnapshotV2,
        *,
        request_id: str,
        item_id: str,
        thread_id: str,
        turn_id: str | None,
    ) -> ThreadSnapshotV2:
        updated = copy_snapshot(snapshot)
        pending = self._find_pending(updated, request_id)
        if pending is None:
            updated["pendingRequests"].append(
                PendingUserInputRequest(
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
        snapshot: ThreadSnapshotV2,
        *,
        request_id: str,
        answers: list[dict[str, Any]],
    ) -> ThreadSnapshotV2:
        updated = copy_snapshot(snapshot)
        pending = self._find_pending(updated, request_id)
        if pending is None:
            raise InvalidRequest(f"Unknown user-input request {request_id!r}.")
        pending["answers"] = list(answers)
        pending["submittedAt"] = iso_now()
        pending["status"] = "answer_submitted"
        return updated

    def mark_answered(
        self,
        snapshot: ThreadSnapshotV2,
        *,
        request_id: str,
    ) -> ThreadSnapshotV2:
        updated = copy_snapshot(snapshot)
        pending = self._find_pending(updated, request_id)
        if pending is None:
            return updated
        pending["status"] = "answered"
        pending["resolvedAt"] = iso_now()
        return updated

    def mark_stale_missing_runtime_requests(
        self,
        snapshot: ThreadSnapshotV2,
        *,
        runtime_request_exists: Any,
    ) -> tuple[ThreadSnapshotV2, bool]:
        updated = copy_snapshot(snapshot)
        changed = False
        for pending in updated.get("pendingRequests", []):
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
    def _find_pending(snapshot: ThreadSnapshotV2, request_id: str) -> PendingUserInputRequest | None:
        for pending in snapshot.get("pendingRequests", []):
            if pending.get("requestId") == request_id:
                return pending
        return None
