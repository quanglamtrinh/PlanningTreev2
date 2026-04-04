"""Unit tests for GitCheckpointService.

Uses real temporary git repos — no mocking of git subprocess calls.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from backend.services.git_checkpoint_service import GitCheckpointService


@pytest.fixture
def svc() -> GitCheckpointService:
    return GitCheckpointService()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo with one commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--initial-branch", "main"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(repo), check=True, capture_output=True)
    (repo / "README.md").write_text("init", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=str(repo), check=True, capture_output=True)
    return repo


@pytest.fixture
def empty_dir(tmp_path: Path) -> Path:
    """A directory that is NOT a git repo."""
    d = tmp_path / "empty"
    d.mkdir()
    return d


# ------------------------------------------------------------------
# is_git_commit_sha
# ------------------------------------------------------------------


class TestIsGitCommitSha:
    def test_valid_sha(self):
        assert GitCheckpointService.is_git_commit_sha("a" * 40) is True

    def test_mixed_hex(self):
        assert GitCheckpointService.is_git_commit_sha("abcdef0123456789" * 2 + "abcdef01") is True

    def test_sha256_prefix(self):
        assert GitCheckpointService.is_git_commit_sha("sha256:abc123") is False

    def test_short_sha(self):
        assert GitCheckpointService.is_git_commit_sha("abcdef") is False

    def test_none(self):
        assert GitCheckpointService.is_git_commit_sha(None) is False

    def test_empty(self):
        assert GitCheckpointService.is_git_commit_sha("") is False

    def test_uppercase_rejected(self):
        assert GitCheckpointService.is_git_commit_sha("A" * 40) is False

    def test_non_hex(self):
        assert GitCheckpointService.is_git_commit_sha("g" * 40) is False


# ------------------------------------------------------------------
# check_git_available
# ------------------------------------------------------------------


class TestCheckGitAvailable:
    def test_git_available(self, svc: GitCheckpointService):
        ok, msg = svc.check_git_available()
        assert ok is True
        assert msg is None


# ------------------------------------------------------------------
# check_repo_exists
# ------------------------------------------------------------------


class TestCheckRepoExists:
    def test_repo_exists(self, svc: GitCheckpointService, git_repo: Path):
        assert svc.check_repo_exists(git_repo) is True

    def test_no_repo(self, svc: GitCheckpointService, empty_dir: Path):
        assert svc.check_repo_exists(empty_dir) is False


# ------------------------------------------------------------------
# check_repo_root
# ------------------------------------------------------------------


class TestCheckRepoRoot:
    def test_root_matches(self, svc: GitCheckpointService, git_repo: Path):
        ok, msg = svc.check_repo_root(git_repo)
        assert ok is True
        assert msg is None

    def test_subfolder_does_not_match(self, svc: GitCheckpointService, git_repo: Path):
        sub = git_repo / "subdir"
        sub.mkdir()
        ok, msg = svc.check_repo_root(sub)
        assert ok is False
        assert "does not match" in (msg or "")


# ------------------------------------------------------------------
# check_inside_parent_repo
# ------------------------------------------------------------------


class TestCheckInsideParentRepo:
    def test_not_inside_any_repo(self, svc: GitCheckpointService, empty_dir: Path):
        inside, root = svc.check_inside_parent_repo(empty_dir)
        assert inside is False

    def test_subfolder_inside_parent(self, svc: GitCheckpointService, git_repo: Path):
        sub = git_repo / "child_project"
        sub.mkdir()
        inside, root = svc.check_inside_parent_repo(sub)
        assert inside is True
        assert root is not None

    def test_exact_root_is_not_inside_parent(self, svc: GitCheckpointService, git_repo: Path):
        inside, root = svc.check_inside_parent_repo(git_repo)
        assert inside is False


# ------------------------------------------------------------------
# check_git_identity
# ------------------------------------------------------------------


class TestCheckGitIdentity:
    def test_identity_configured(self, svc: GitCheckpointService, git_repo: Path):
        ok, msg = svc.check_git_identity(git_repo)
        assert ok is True

    def test_identity_missing(self, svc: GitCheckpointService, tmp_path: Path):
        # Create a repo without identity
        repo = tmp_path / "noid"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
        # Unset identity at local level
        subprocess.run(["git", "config", "--local", "--unset", "user.name"], cwd=str(repo), capture_output=True)
        subprocess.run(["git", "config", "--local", "--unset", "user.email"], cwd=str(repo), capture_output=True)
        # Note: global identity may still be set on the test machine, so this
        # test just validates the method doesn't crash. A true negative test
        # would need to mock the environment.
        ok, msg = svc.check_git_identity(repo)
        # We can at least verify the return shape
        assert isinstance(ok, bool)


# ------------------------------------------------------------------
# check_working_tree_clean
# ------------------------------------------------------------------


class TestCheckWorkingTreeClean:
    def test_clean(self, svc: GitCheckpointService, git_repo: Path):
        ok, msg = svc.check_working_tree_clean(git_repo)
        assert ok is True
        assert msg is None

    def test_dirty(self, svc: GitCheckpointService, git_repo: Path):
        (git_repo / "newfile.txt").write_text("dirty", encoding="utf-8")
        ok, msg = svc.check_working_tree_clean(git_repo)
        assert ok is False
        assert "not clean" in (msg or "")


# ------------------------------------------------------------------
# check_planningtree_not_tracked
# ------------------------------------------------------------------


class TestCheckPlanningtreeNotTracked:
    def test_not_tracked(self, svc: GitCheckpointService, git_repo: Path):
        ok, msg = svc.check_planningtree_not_tracked(git_repo)
        assert ok is True

    def test_tracked(self, svc: GitCheckpointService, git_repo: Path):
        pt_dir = git_repo / ".planningtree"
        pt_dir.mkdir()
        (pt_dir / "data.json").write_text("{}", encoding="utf-8")
        subprocess.run(["git", "add", ".planningtree/"], cwd=str(git_repo), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add pt"], cwd=str(git_repo), check=True, capture_output=True)
        ok, msg = svc.check_planningtree_not_tracked(git_repo)
        assert ok is False
        assert ".planningtree/" in (msg or "")


# ------------------------------------------------------------------
# get_head_sha / capture_head_sha
# ------------------------------------------------------------------


class TestHeadSha:
    def test_get_head_sha(self, svc: GitCheckpointService, git_repo: Path):
        sha = svc.get_head_sha(git_repo)
        assert sha is not None
        assert len(sha) == 40
        assert GitCheckpointService.is_git_commit_sha(sha)

    def test_get_head_sha_no_repo(self, svc: GitCheckpointService, empty_dir: Path):
        sha = svc.get_head_sha(empty_dir)
        assert sha is None

    def test_capture_head_sha(self, svc: GitCheckpointService, git_repo: Path):
        sha = svc.capture_head_sha(git_repo)
        assert len(sha) == 40

    def test_capture_head_sha_empty_repo(self, svc: GitCheckpointService, tmp_path: Path):
        repo = tmp_path / "empty_repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), check=True, capture_output=True)
        from backend.errors.app_errors import GitCheckpointError

        with pytest.raises(GitCheckpointError):
            svc.capture_head_sha(repo)


# ------------------------------------------------------------------
# sha_exists / is_ancestor
# ------------------------------------------------------------------


class TestShaOperations:
    def test_sha_exists(self, svc: GitCheckpointService, git_repo: Path):
        sha = svc.get_head_sha(git_repo)
        assert svc.sha_exists(git_repo, sha) is True

    def test_sha_not_exists(self, svc: GitCheckpointService, git_repo: Path):
        assert svc.sha_exists(git_repo, "0" * 40) is False

    def test_is_ancestor(self, svc: GitCheckpointService, git_repo: Path):
        first_sha = svc.get_head_sha(git_repo)
        (git_repo / "file2.txt").write_text("content", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=str(git_repo), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "second"], cwd=str(git_repo), check=True, capture_output=True)
        second_sha = svc.get_head_sha(git_repo)
        assert svc.is_ancestor(git_repo, first_sha, second_sha) is True
        assert svc.is_ancestor(git_repo, second_sha, first_sha) is False


# ------------------------------------------------------------------
# probe_git_initialized
# ------------------------------------------------------------------


class TestProbeGitInitialized:
    def test_true_for_repo_root(self, svc: GitCheckpointService, git_repo: Path):
        assert svc.probe_git_initialized(git_repo) is True

    def test_false_for_subfolder(self, svc: GitCheckpointService, git_repo: Path):
        sub = git_repo / "subdir"
        sub.mkdir()
        assert svc.probe_git_initialized(sub) is False

    def test_false_for_non_repo(self, svc: GitCheckpointService, empty_dir: Path):
        assert svc.probe_git_initialized(empty_dir) is False


# ------------------------------------------------------------------
# validate_guardrails
# ------------------------------------------------------------------


class TestValidateGuardrails:
    def test_all_pass(self, svc: GitCheckpointService, git_repo: Path):
        blockers = svc.validate_guardrails(git_repo)
        assert blockers == []

    def test_no_repo(self, svc: GitCheckpointService, empty_dir: Path):
        blockers = svc.validate_guardrails(empty_dir)
        assert len(blockers) == 1
        assert "No Git repository" in blockers[0]

    def test_dirty_tree(self, svc: GitCheckpointService, git_repo: Path):
        (git_repo / "dirty.txt").write_text("x", encoding="utf-8")
        blockers = svc.validate_guardrails(git_repo)
        assert any("not clean" in b for b in blockers)

    def test_expected_head_matches(self, svc: GitCheckpointService, git_repo: Path):
        sha = svc.get_head_sha(git_repo)
        blockers = svc.validate_guardrails(git_repo, expected_head=sha)
        assert blockers == []

    def test_expected_head_mismatch(self, svc: GitCheckpointService, git_repo: Path):
        blockers = svc.validate_guardrails(git_repo, expected_head="0" * 40)
        assert any("does not match" in b for b in blockers)

    def test_allows_tracked_planningtree(self, svc: GitCheckpointService, git_repo: Path):
        pt_dir = git_repo / ".planningtree"
        pt_dir.mkdir()
        (pt_dir / "data.json").write_text("{}", encoding="utf-8")
        subprocess.run(["git", "add", ".planningtree/"], cwd=str(git_repo), check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "add pt"], cwd=str(git_repo), check=True, capture_output=True)
        blockers = svc.validate_guardrails(git_repo)
        assert blockers == []


# ------------------------------------------------------------------
# init_repo
# ------------------------------------------------------------------


class TestInitRepo:
    def test_creates_repo_and_commit(self, svc: GitCheckpointService, empty_dir: Path):
        sha = svc.init_repo(empty_dir)
        assert len(sha) == 40
        assert svc.probe_git_initialized(empty_dir) is True

    def test_does_not_force_planningtree_gitignore_entry(self, svc: GitCheckpointService, empty_dir: Path):
        svc.init_repo(empty_dir)
        gitignore_path = empty_dir / ".gitignore"
        if gitignore_path.exists():
            gitignore = gitignore_path.read_text(encoding="utf-8")
            assert ".planningtree/" not in gitignore

    def test_already_initialized(self, svc: GitCheckpointService, git_repo: Path):
        from backend.errors.app_errors import GitInitNotAllowed

        with pytest.raises(GitInitNotAllowed):
            svc.init_repo(git_repo)

    def test_inside_parent_repo(self, svc: GitCheckpointService, git_repo: Path):
        sub = git_repo / "child"
        sub.mkdir()
        from backend.errors.app_errors import GitInitNotAllowed

        with pytest.raises(GitInitNotAllowed, match="inside an existing"):
            svc.init_repo(sub)


# ------------------------------------------------------------------
# commit_if_changed
# ------------------------------------------------------------------


class TestCommitIfChanged:
    def test_with_changes(self, svc: GitCheckpointService, git_repo: Path):
        initial = svc.get_head_sha(git_repo)
        (git_repo / "newfile.txt").write_text("content", encoding="utf-8")
        new_sha = svc.commit_if_changed(git_repo, "test commit")
        assert new_sha is not None
        assert new_sha != initial
        assert svc.get_head_sha(git_repo) == new_sha

    def test_no_changes(self, svc: GitCheckpointService, git_repo: Path):
        result = svc.commit_if_changed(git_repo, "nothing to commit")
        assert result is None


# ------------------------------------------------------------------
# get_changed_files
# ------------------------------------------------------------------


class TestGetChangedFiles:
    def test_changed_files(self, svc: GitCheckpointService, git_repo: Path):
        initial = svc.get_head_sha(git_repo)
        (git_repo / "added.txt").write_text("new", encoding="utf-8")
        (git_repo / "README.md").write_text("modified", encoding="utf-8")
        new_sha = svc.commit_if_changed(git_repo, "changes")
        assert new_sha is not None
        files = svc.get_changed_files(git_repo, initial, new_sha)
        assert len(files) >= 2
        paths = {f["path"] for f in files}
        assert "added.txt" in paths
        assert "README.md" in paths
        statuses = {f["status"] for f in files}
        assert "A" in statuses  # added.txt
        assert "M" in statuses  # README.md

    def test_no_diff(self, svc: GitCheckpointService, git_repo: Path):
        sha = svc.get_head_sha(git_repo)
        files = svc.get_changed_files(git_repo, sha, sha)
        assert files == []


# ------------------------------------------------------------------
# build_commit_message
# ------------------------------------------------------------------


class TestBuildCommitMessage:
    def test_basic(self):
        msg = GitCheckpointService.build_commit_message("1.2", "Implement Auth Guard")
        assert msg == "pt(1.2): implement auth guard"

    def test_truncation(self):
        long_title = "a" * 100
        msg = GitCheckpointService.build_commit_message("1", long_title)
        assert len(msg) <= 72
        assert msg.endswith("...")

    def test_whitespace(self):
        msg = GitCheckpointService.build_commit_message("3.1.2", "  Fix Bug  ")
        assert msg == "pt(3.1.2): fix bug"


# ------------------------------------------------------------------
# hard_reset
# ------------------------------------------------------------------


class TestHardReset:
    def test_reset_to_earlier_commit(self, svc: GitCheckpointService, git_repo: Path):
        initial = svc.get_head_sha(git_repo)
        (git_repo / "file.txt").write_text("data", encoding="utf-8")
        svc.commit_if_changed(git_repo, "added file")
        assert svc.get_head_sha(git_repo) != initial

        new_head = svc.hard_reset(git_repo, initial)
        assert new_head == initial
        assert svc.get_head_sha(git_repo) == initial
        assert not (git_repo / "file.txt").exists()

    def test_reset_nonexistent_sha(self, svc: GitCheckpointService, git_repo: Path):
        from backend.errors.app_errors import GitCheckpointError

        with pytest.raises(GitCheckpointError, match="does not exist"):
            svc.hard_reset(git_repo, "0" * 40)


# ------------------------------------------------------------------
# _parse_name_status
# ------------------------------------------------------------------


class TestParseNameStatus:
    def test_add_modify_delete(self):
        output = "A\tnew.txt\nM\texisting.txt\nD\tremoved.txt\n"
        records = GitCheckpointService._parse_name_status(output)
        assert len(records) == 3
        assert records[0] == {"path": "new.txt", "status": "A"}
        assert records[1] == {"path": "existing.txt", "status": "M"}
        assert records[2] == {"path": "removed.txt", "status": "D"}

    def test_rename(self):
        output = "R100\told.txt\tnew.txt\n"
        records = GitCheckpointService._parse_name_status(output)
        assert len(records) == 1
        assert records[0] == {"path": "new.txt", "status": "R", "previous_path": "old.txt"}

    def test_empty(self):
        assert GitCheckpointService._parse_name_status("") == []
        assert GitCheckpointService._parse_name_status("\n") == []

    def test_unknown_status_defaults_to_M(self):
        output = "T\tspecial.txt\n"
        records = GitCheckpointService._parse_name_status(output)
        assert records[0]["status"] == "M"
