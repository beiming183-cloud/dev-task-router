from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .executor import CommandExecutor, ExecutionRequest
from .models import TaskRole, TaskSpec
from .router import RoutingDecision


@dataclass(frozen=True, slots=True)
class CheckReport:
    ok: bool
    message: str
    evidence: str = ""
    returncode: int | None = None
    failure_type: str | None = None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError:
        return None


def git_snapshot(root: Path) -> str | None:
    """Return a content-sensitive snapshot of tracked, staged and untracked changes."""
    probe = _git(root, "rev-parse", "--is-inside-work-tree")
    if probe is None or probe.returncode != 0 or probe.stdout.strip() != "true":
        return None

    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    unstaged = _git(root, "diff", "--no-ext-diff", "--binary")
    staged = _git(root, "diff", "--cached", "--no-ext-diff", "--binary")
    if any(item is None or item.returncode != 0 for item in (status, unstaged, staged)):
        return None

    untracked_hashes: list[str] = []
    for line in status.stdout.splitlines():
        if not line.startswith("?? "):
            continue
        relative = line[3:]
        path = root / relative
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        untracked_hashes.append(f"{relative}:{digest}")

    return "\n".join(
        [
            "[status]",
            status.stdout,
            "[unstaged]",
            unstaged.stdout,
            "[staged]",
            staged.stdout,
            "[untracked-hashes]",
            "\n".join(untracked_hashes),
        ]
    )


class TaskChecker:
    def __init__(self, command_executor: CommandExecutor | None = None):
        self.command_executor = command_executor or CommandExecutor()

    def run(
        self,
        task: TaskSpec,
        *,
        root: Path,
        route: RoutingDecision,
        before_git: str | None,
    ) -> CheckReport:
        output: list[str] = []
        for index, check in enumerate(task.checks, 1):
            request = ExecutionRequest(
                task_id=f"{task.id}:check:{index}",
                command=check,
                prompt=None,
                cwd=root,
                role=TaskRole.EXECUTOR,
                route=route,
            )
            result = self.command_executor.run(request)
            if result.stdout.strip():
                output.append(result.stdout.strip())
            if result.returncode != 0:
                message = result.stderr.strip() or f"check {index} exited {result.returncode}"
                return CheckReport(
                    False,
                    message,
                    "\n".join(output),
                    result.returncode,
                    "CHECK",
                )

        if task.require_diff:
            after_git = git_snapshot(root)
            if before_git is None or after_git is None:
                return CheckReport(
                    False,
                    "require_diff needs a Git worktree",
                    "\n".join(output),
                    None,
                    "DIFF",
                )
            if before_git == after_git:
                return CheckReport(
                    False,
                    "task required a Git change but working tree did not change",
                    after_git,
                    None,
                    "DIFF",
                )
            output.append(after_git.strip())

        return CheckReport(True, "checks passed", "\n".join(item for item in output if item))
