"""Git subprocess operations for task checkpoint lifecycle.

Stateless service — all state lives in the git repo itself.
Every git command runs via ``_run_git`` with a 30-second default timeout.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

from backend.errors.app_errors import GitCheckpointError, GitInitNotAllowed

logger = logging.getLogger(__name__)

_GIT_COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class GitCheckpointService:
    """Pure git subprocess wrapper for checkpoint operations."""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _run_git(
        args: list[str],
        cwd: Path,
        *,
        check: bool = True,
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        cmd = ["git", *args]
        try:
            return subprocess.run(
                cmd,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=check,
                timeout=timeout,
            )
        except FileNotFoundError:
            raise GitCheckpointError("Git is not installed or not on PATH.")
        except subprocess.TimeoutExpired as exc:
            raise GitCheckpointError(
                f"Git command timed out after {timeout}s: {' '.join(cmd)}"
            ) from exc
        except subprocess.CalledProcessError as exc:
            if check:
                stderr = (exc.stderr or "").strip()
                raise GitCheckpointError(
                    f"Git command failed (exit {exc.returncode}): {stderr}"
                ) from exc
            raise  # unreachable when check=False, but keeps mypy happy

    @staticmethod
    def _ensure_gitignore_entry(project_path: Path, entry: str) -> bool:
        """Append *entry* to ``.gitignore`` if not already present.

        Returns True if the entry was added, False if already present.
        """
        gitignore = project_path / ".gitignore"
        if gitignore.exists():
            content = gitignore.read_text(encoding="utf-8")
            for line in content.splitlines():
                if line.strip() == entry:
                    return False
            if content and not content.endswith("\n"):
                content += "\n"
        else:
            content = ""
        content += entry + "\n"
        gitignore.write_text(content, encoding="utf-8")
        return True

    @staticmethod
    def _parse_name_status(output: str) -> list[dict[str, Any]]:
        """Parse ``git diff --name-status`` output into ChangedFileRecord dicts."""
        records: list[dict[str, Any]] = []
        for line in output.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            raw_status = parts[0]
            # Rename: R100\told\tnew
            if raw_status.startswith("R"):
                status = "R"
                previous_path = parts[1] if len(parts) >= 3 else None
                path = parts[2] if len(parts) >= 3 else parts[1]
                records.append(
                    {"path": path, "status": status, "previous_path": previous_path}
                )
            else:
                status_char = raw_status[0] if raw_status else "M"
                if status_char not in ("A", "M", "D", "R"):
                    status_char = "M"
                records.append({"path": parts[1], "status": status_char})
        return records

    @staticmethod
    def _parse_porcelain_status(output: str) -> list[dict[str, Any]]:
        """Parse ``git status --porcelain=v1`` output."""
        records: list[dict[str, Any]] = []
        for line in output.splitlines():
            if len(line) < 4:
                continue
            xy = line[:2]
            path = line[3:]
            # Use index status (first char) preferring it over worktree status
            index_status = xy[0].strip()
            worktree_status = xy[1].strip()
            status = index_status or worktree_status or "M"
            if status == "?":
                status = "A"
            elif status not in ("A", "M", "D", "R"):
                status = "M"
            # Handle rename: "R  old -> new"
            if " -> " in path:
                old, new = path.split(" -> ", 1)
                records.append(
                    {"path": new, "status": "R", "previous_path": old}
                )
            else:
                records.append({"path": path, "status": status})
        return records

    # ------------------------------------------------------------------
    # Public: checks
    # ------------------------------------------------------------------

    def check_git_available(self) -> tuple[bool, str | None]:
        """Return (True, None) if ``git`` is on PATH, else (False, message)."""
        try:
            self._run_git(["--version"], cwd=Path("."))
            return True, None
        except GitCheckpointError:
            return False, "Git is not installed or not on PATH."

    def check_repo_exists(self, project_path: Path) -> bool:
        """Return True if *project_path* is inside a git repo."""
        try:
            result = self._run_git(
                ["-C", str(project_path), "rev-parse", "--git-dir"],
                cwd=project_path,
                check=False,
            )
            return result.returncode == 0
        except GitCheckpointError:
            return False

    def check_repo_root(
        self, project_path: Path
    ) -> tuple[bool, str | None]:
        """Return (True, None) if repo root == *project_path*."""
        try:
            result = self._run_git(
                ["-C", str(project_path), "rev-parse", "--show-toplevel"],
                cwd=project_path,
            )
            actual = Path(result.stdout.strip()).resolve()
            expected = project_path.resolve()
            if actual == expected:
                return True, None
            return False, (
                f"Git repository root ({actual}) does not match "
                f"project path ({expected})."
            )
        except GitCheckpointError:
            return False, "Could not determine git repository root."

    def check_inside_parent_repo(
        self, project_path: Path
    ) -> tuple[bool, str | None]:
        """Return (True, parent_root) if *project_path* is inside a git repo
        rooted elsewhere. Returns (False, None) if not inside any repo or if
        repo root matches project_path exactly.
        """
        try:
            result = self._run_git(
                ["-C", str(project_path), "rev-parse", "--show-toplevel"],
                cwd=project_path,
                check=False,
            )
            if result.returncode != 0:
                return False, None
            actual_root = Path(result.stdout.strip()).resolve()
            if actual_root == project_path.resolve():
                return False, None
            return True, str(actual_root)
        except GitCheckpointError:
            return False, None

    def check_git_identity(
        self, project_path: Path
    ) -> tuple[bool, str | None]:
        """Return (True, None) if user.name and user.email are configured."""
        try:
            name_result = self._run_git(
                ["config", "user.name"], cwd=project_path, check=False
            )
            email_result = self._run_git(
                ["config", "user.email"], cwd=project_path, check=False
            )
            name = (name_result.stdout or "").strip()
            email = (email_result.stdout or "").strip()
            if name and email:
                return True, None
            return False, (
                "Git identity not configured. "
                "Run: git config user.name '...' && git config user.email '...'"
            )
        except GitCheckpointError:
            return False, "Could not check git identity configuration."

    def check_working_tree_clean(
        self, project_path: Path
    ) -> tuple[bool, str | None]:
        """Return (True, None) if working tree has no uncommitted changes."""
        try:
            result = self._run_git(
                ["-C", str(project_path), "status", "--porcelain=v1"],
                cwd=project_path,
            )
            if result.stdout.strip():
                return False, (
                    "Working tree is not clean. "
                    "Commit or discard changes before running this task."
                )
            return True, None
        except GitCheckpointError:
            return False, "Could not check working tree status."

    def check_planningtree_not_tracked(
        self, project_path: Path
    ) -> tuple[bool, str | None]:
        """Return (True, None) if ``.planningtree/`` is NOT tracked by git."""
        try:
            result = self._run_git(
                [
                    "-C",
                    str(project_path),
                    "ls-files",
                    "--error-unmatch",
                    ".planningtree/",
                ],
                cwd=project_path,
                check=False,
            )
            if result.returncode != 0:
                # exit 1 = not tracked = good
                return True, None
            return False, (
                ".planningtree/ is tracked by Git. "
                "Remove from tracking: git rm -r --cached .planningtree/"
            )
        except GitCheckpointError:
            return True, None  # If git fails, assume not tracked

    # ------------------------------------------------------------------
    # Public: SHA operations
    # ------------------------------------------------------------------

    def get_head_sha(self, project_path: Path) -> str | None:
        """Return HEAD commit SHA, or None if repo has no commits."""
        try:
            result = self._run_git(
                ["-C", str(project_path), "rev-parse", "HEAD"],
                cwd=project_path,
                check=False,
            )
            if result.returncode != 0:
                return None
            sha = result.stdout.strip()
            return sha if sha else None
        except GitCheckpointError:
            return None

    def capture_head_sha(self, project_path: Path) -> str:
        """Like ``get_head_sha`` but raises if None."""
        sha = self.get_head_sha(project_path)
        if sha is None:
            raise GitCheckpointError(
                "Cannot capture HEAD SHA: repository has no commits."
            )
        return sha

    def sha_exists(self, project_path: Path, sha: str) -> bool:
        """Return True if *sha* exists as a valid git object."""
        try:
            result = self._run_git(
                ["-C", str(project_path), "cat-file", "-t", sha],
                cwd=project_path,
                check=False,
            )
            return result.returncode == 0
        except GitCheckpointError:
            return False

    def is_ancestor(
        self, project_path: Path, ancestor_sha: str, descendant_sha: str
    ) -> bool:
        """Return True if *ancestor_sha* is an ancestor of *descendant_sha*."""
        try:
            result = self._run_git(
                [
                    "-C",
                    str(project_path),
                    "merge-base",
                    "--is-ancestor",
                    ancestor_sha,
                    descendant_sha,
                ],
                cwd=project_path,
                check=False,
            )
            return result.returncode == 0
        except GitCheckpointError:
            return False

    @staticmethod
    def is_git_commit_sha(value: str | None) -> bool:
        """Return True if *value* is a 40-char hex string (git commit SHA)."""
        if not value:
            return False
        return bool(_GIT_COMMIT_SHA_RE.match(value))

    # ------------------------------------------------------------------
    # Public: probe / validate
    # ------------------------------------------------------------------

    def probe_git_initialized(self, project_path: Path) -> bool:
        """Return True only if git is available, repo exists, AND repo root
        matches *project_path* exactly. A subfolder inside a parent repo
        returns False.
        """
        available, _ = self.check_git_available()
        if not available:
            return False
        if not self.check_repo_exists(project_path):
            return False
        root_ok, _ = self.check_repo_root(project_path)
        return root_ok

    def validate_guardrails(
        self, project_path: Path, *, expected_head: str | None = None
    ) -> list[str]:
        """Run all guardrail checks. Returns list of blocker messages (empty = pass)."""
        blockers: list[str] = []

        # Check 1: git available
        ok, msg = self.check_git_available()
        if not ok:
            blockers.append(msg or "Git is not available.")
            return blockers  # Can't run further checks

        # Check 2: repo exists
        if not self.check_repo_exists(project_path):
            blockers.append(
                "No Git repository found. Initialize Git for this project first."
            )
            return blockers

        # Check 3: repo root match
        ok, msg = self.check_repo_root(project_path)
        if not ok:
            blockers.append(msg or "Git repository root mismatch.")
            return blockers

        # Check 4: .planningtree not tracked
        ok, msg = self.check_planningtree_not_tracked(project_path)
        if not ok:
            blockers.append(msg or ".planningtree/ is tracked by Git.")

        # Check 5: identity configured
        ok, msg = self.check_git_identity(project_path)
        if not ok:
            blockers.append(msg or "Git identity not configured.")

        # Check 6: working tree clean
        ok, msg = self.check_working_tree_clean(project_path)
        if not ok:
            blockers.append(msg or "Working tree is not clean.")

        # Check 7: HEAD matches expected (only when expected_head provided)
        if expected_head is not None and not blockers:
            head = self.get_head_sha(project_path)
            if head != expected_head:
                blockers.append(
                    f"HEAD ({head}) does not match expected baseline ({expected_head})."
                )

        return blockers

    # ------------------------------------------------------------------
    # Public: init
    # ------------------------------------------------------------------

    def init_repo(self, project_path: Path) -> str:
        """Initialize a git repo at *project_path* and return the initial commit SHA.

        Raises ``GitInitNotAllowed`` if *project_path* is inside an existing repo.
        """
        inside, parent_root = self.check_inside_parent_repo(project_path)
        if inside:
            raise GitInitNotAllowed(
                f"Project folder is inside an existing Git repository at {parent_root}. "
                "Initialize Git at the project root instead, or move the project folder."
            )

        if self.check_repo_exists(project_path):
            root_ok, _ = self.check_repo_root(project_path)
            if root_ok:
                raise GitInitNotAllowed(
                    "A Git repository already exists at this project path."
                )

        # git init
        try:
            self._run_git(
                ["init", "--initial-branch", "main"],
                cwd=project_path,
            )
        except GitCheckpointError:
            # Fallback for older git without --initial-branch
            self._run_git(["init"], cwd=project_path)
            try:
                self._run_git(
                    ["branch", "-m", "main"], cwd=project_path, check=False
                )
            except GitCheckpointError:
                pass  # Best-effort rename

        # Ensure .planningtree/ in .gitignore
        self._ensure_gitignore_entry(project_path, ".planningtree/")

        # Stage and create initial commit
        self._run_git(["-C", str(project_path), "add", "-A"], cwd=project_path)
        self._run_git(
            [
                "-C",
                str(project_path),
                "commit",
                "-m",
                "Initial commit (PlanningTree)",
                "--allow-empty",
            ],
            cwd=project_path,
        )
        return self.capture_head_sha(project_path)

    # ------------------------------------------------------------------
    # Public: commit / changed files
    # ------------------------------------------------------------------

    def commit_if_changed(
        self, project_path: Path, commit_message: str
    ) -> str | None:
        """Stage all changes, commit if there are diffs, return new HEAD SHA
        or None if nothing changed.

        This is a critical operation — failures should propagate.
        """
        # Stage everything (.planningtree/ excluded via .gitignore)
        self._run_git(["-C", str(project_path), "add", "-A"], cwd=project_path)

        # Check for staged changes
        result = self._run_git(
            ["-C", str(project_path), "diff", "--cached", "--quiet"],
            cwd=project_path,
            check=False,
        )
        if result.returncode == 0:
            return None  # No changes

        # Commit
        self._run_git(
            ["-C", str(project_path), "commit", "-m", commit_message],
            cwd=project_path,
        )
        return self.capture_head_sha(project_path)

    def get_changed_files(
        self, project_path: Path, from_sha: str, to_sha: str
    ) -> list[dict[str, Any]]:
        """Return list of ChangedFileRecord dicts between two commits.

        Best-effort — failures are logged and return [].
        """
        try:
            result = self._run_git(
                [
                    "-C",
                    str(project_path),
                    "diff",
                    "--name-status",
                    from_sha,
                    to_sha,
                ],
                cwd=project_path,
            )
            return self._parse_name_status(result.stdout)
        except GitCheckpointError:
            logger.warning(
                "Failed to get changed files between %s and %s",
                from_sha,
                to_sha,
                exc_info=True,
            )
            return []

    def get_diff(self, project_path: Path, from_sha: str, to_sha: str) -> str:
        """Return raw unified diff between two commits.

        Best-effort — raises GitCheckpointError on failure.
        """
        result = self._run_git(
            ["-C", str(project_path), "diff", from_sha, to_sha],
            cwd=project_path,
        )
        return result.stdout

    @staticmethod
    def build_commit_message(hierarchical_number: str, title: str) -> str:
        """Format: ``pt(1.2): implement auth guard`` (truncated to 72 chars)."""
        prefix = f"pt({hierarchical_number}): "
        title_lower = title.lower().strip()
        message = prefix + title_lower
        if len(message) > 72:
            message = message[:69] + "..."
        return message

    # ------------------------------------------------------------------
    # Public: reset
    # ------------------------------------------------------------------

    def hard_reset(self, project_path: Path, target_sha: str) -> str:
        """``git reset --hard {target_sha}``. Returns the new HEAD SHA."""
        if not self.sha_exists(project_path, target_sha):
            raise GitCheckpointError(
                f"Target SHA {target_sha} does not exist in the repository."
            )
        self._run_git(
            ["-C", str(project_path), "reset", "--hard", target_sha],
            cwd=project_path,
        )
        new_head = self.capture_head_sha(project_path)
        if new_head != target_sha:
            raise GitCheckpointError(
                f"Reset verification failed: HEAD is {new_head}, expected {target_sha}."
            )
        return new_head
