from __future__ import annotations

import re
from pathlib import Path


def test_no_production_callsites_use_legacy_append_immutable_audit_record() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    scan_targets = [
        repo_root / "backend" / "services",
        repo_root / "backend" / "routes",
        repo_root / "backend" / "main.py",
    ]
    pattern = re.compile(r"\bappend_immutable_audit_record\(")

    hits: list[tuple[str, int, str]] = []
    for target in scan_targets:
        if target.is_dir():
            paths = sorted(target.rglob("*.py"))
        else:
            paths = [target]
        for path in paths:
            relpath = path.relative_to(repo_root).as_posix()
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if pattern.search(line):
                    hits.append((relpath, lineno, line.strip()))

    assert len(hits) == 1
    relpath, _, line = hits[0]
    assert relpath == "backend/services/execution_gating.py"
    assert line.startswith("def append_immutable_audit_record(")
