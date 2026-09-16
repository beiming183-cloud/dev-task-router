from __future__ import annotations

import json
import subprocess

import pytest

from dev_task_router.config import (
    load_rolling_context,
    save_repository_context,
    save_rolling_context,
    write_default_files,
)
from dev_task_router.loop_cli import main
from dev_task_router.repo_context import RepositoryContext
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


def _project(tmp_path, *, ci_status: str = "success") -> str:
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
            {"project": "demo", "last_commit": "older"}
        ),
    )
    save_repository_context(
        tmp_path,
        RepositoryContext(
            repository="owner/repo",
            branch="main",
            commit=head,
            ci_status=ci_status,
            source="github",
        ),
    )
    return head


def test_sync_repository_cli_accepts_verified_clean_anchor(tmp_path, capsys) -> None:
    head = _project(tmp_path)

    code = main(["--root", str(tmp_path), "sync-repository", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["accepted"] is True
    assert payload["status"] == "ACCEPTED"
    assert payload["commit"] == head
    assert load_rolling_context(tmp_path, project="demo").last_commit == head


def test_sync_repository_cli_blocks_non_success_ci(tmp_path, capsys) -> None:
    _project(tmp_path, ci_status="pending")

    code = main(["--root", str(tmp_path), "sync-repository", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["accepted"] is False
    assert payload["status"] == "CI_NOT_SUCCESS"
    assert load_rolling_context(tmp_path, project="demo").last_commit == "older"
