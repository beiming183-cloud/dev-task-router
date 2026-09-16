from __future__ import annotations

import subprocess

import pytest

from dev_task_router.config import (
    load_rolling_context,
    save_repository_context,
    save_rolling_context,
    write_default_files,
)
from dev_task_router.repo_context import RepositoryContext
from dev_task_router.repository_reconcile import RepositoryEvidenceReconciler
from dev_task_router.rolling_context import RollingProjectContext


def _git(root, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _repo(tmp_path):
    try:
        _git(tmp_path, "init")
    except (FileNotFoundError, subprocess.CalledProcessError):
        pytest.skip("git unavailable")
    (tmp_path / ".gitignore").write_text(".autodev/\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(tmp_path, "add", ".gitignore", "app.py")
    _git(
        tmp_path,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=test",
        "commit",
        "-m",
        "initial",
    )
    head = _git(tmp_path, "rev-parse", "HEAD")
    write_default_files(tmp_path, "demo")
    save_rolling_context(
        tmp_path,
        RollingProjectContext.from_dict(
            {
                "project": "demo",
                "goal": "test repository reconciliation",
                "last_commit": "older-anchor",
            }
        ),
    )
    return head


def _context(tmp_path, commit: str, *, ci_status: str = "success") -> None:
    save_repository_context(
        tmp_path,
        RepositoryContext(
            repository="owner/repo",
            branch="feature/test",
            commit=commit,
            ci_status=ci_status,
            source="github",
        ),
    )


def test_accepts_anchor_only_when_github_ci_head_and_worktree_agree(tmp_path) -> None:
    head = _repo(tmp_path)
    _context(tmp_path, head)

    result = RepositoryEvidenceReconciler(tmp_path).reconcile()
    rolling = load_rolling_context(tmp_path, project="demo")

    assert result.accepted is True
    assert result.status == "ACCEPTED"
    assert result.local_head == head
    assert rolling.last_commit == head


def test_ci_failure_blocks_anchor_advance(tmp_path) -> None:
    head = _repo(tmp_path)
    _context(tmp_path, head, ci_status="failure")

    result = RepositoryEvidenceReconciler(tmp_path).reconcile()

    assert result.accepted is False
    assert result.status == "CI_NOT_SUCCESS"
    assert load_rolling_context(tmp_path, project="demo").last_commit == "older-anchor"


def test_local_head_mismatch_blocks_anchor_advance(tmp_path) -> None:
    _repo(tmp_path)
    _context(tmp_path, "deadbeef")

    result = RepositoryEvidenceReconciler(tmp_path).reconcile()

    assert result.accepted is False
    assert result.status == "LOCAL_HEAD_MISMATCH"
    assert load_rolling_context(tmp_path, project="demo").last_commit == "older-anchor"


def test_uncommitted_business_change_blocks_anchor_advance(tmp_path) -> None:
    head = _repo(tmp_path)
    _context(tmp_path, head)
    (tmp_path / "app.py").write_text("VALUE = 2\n", encoding="utf-8")

    result = RepositoryEvidenceReconciler(tmp_path).reconcile()

    assert result.accepted is False
    assert result.status == "LOCAL_WORKTREE_DIRTY"
    assert result.dirty_paths == ("app.py",)
    assert load_rolling_context(tmp_path, project="demo").last_commit == "older-anchor"


def test_autodev_metadata_changes_do_not_make_business_tree_dirty(tmp_path) -> None:
    head = _repo(tmp_path)
    _context(tmp_path, head)
    # AutoDev runtime/config is intentionally outside the business/source cleanliness gate.
    (tmp_path / ".autodev" / "temporary-runtime.txt").write_text("runtime", encoding="utf-8")

    result = RepositoryEvidenceReconciler(tmp_path).reconcile()

    assert result.accepted is True
    assert load_rolling_context(tmp_path, project="demo").last_commit == head
