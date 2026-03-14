from __future__ import annotations

import re

from backend.errors.app_errors import InvalidProjectId

_PROJECT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def normalize_project_id(project_id: str) -> str:
    normalized = str(project_id or "").strip()
    if not _PROJECT_ID_PATTERN.fullmatch(normalized):
        raise InvalidProjectId(project_id)
    return normalized
