from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .config import (
    load_repository_context,
    load_rolling_context,
    save_rolling_context,
)
from .execution_evidence import ExecutionEvidenceLedger
from .state import now_iso


@dataclass(frozen=True, slots=True)
class RepositoryReconcileResult:
    accepted: bool
    status: str
    message: str
    repository: str | None = None
    commit: str | None = None
    ci_status: str | None = None
    local_head: str | None = None
    dirty_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "status": self.status,
            "message": self.message,
            "repository": self.repository,
            "commit": self.commit,
            "ci_status": self.ci_status,
            "local_head": self.local_head,
            "dirty_paths": list(self.dirty_paths),
        }


class RepositoryEvidenceReconciler:
    """Accept a new rolling commit anchor only when local and GitHub facts agree."""

    def __init__(
        self,
        root: Path,
        *,
        evidence: ExecutionEvidenceLedger | None = None,
    ):
        self.root = root
        self.evidence = evidence or ExecutionEvidenceLedger(root)

    def _git(self, *args: str) -> subprocess.CompletedProcess[str] | None:
        try:
            return subprocess.run(
                ["git", *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError:
            return None

    @staticmethod
    def _status_path(line: str) -> str:
        value = line[3:].strip() if len(line) >= 4 else ""
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        return value.strip('"')

    def _business_dirty_paths(self) -> tuple[str, ...] | None:
        result = self._git("status", "--porcelain", "--untracked-files=all")
        if result is None or result.returncode != 0:
            return None
        paths: list[str] = []
        for line in result.stdout.splitlines():
            path = self._status_path(line)
            normalized = path.replace("\\", "/")
            # AutoDev metadata may change while the business/source tree is clean.
            if not normalized or normalized == ".autodev" or normalized.startswith(".autodev/"):
                continue
            paths.append(normalized)
        return tuple(paths)

    def reconcile(self, *, require_ci_success: bool = True) -> RepositoryReconcileResult:
        repository = load_repository_context(self.root)
        if repository is None:
            return RepositoryReconcileResult(
                False,
                "NO_REPOSITORY_CONTEXT",
                "no repository context is available; refresh verified GitHub evidence first",
            )
        if not repository.commit:
            return RepositoryReconcileResult(
                False,
                "UNANCHORED_REPOSITORY_CONTEXT",
                "repository context has no concrete commit SHA",
                repository.repository,
                None,
                repository.ci_status,
            )
        if require_ci_success and repository.ci_status != "success":
            return RepositoryReconcileResult(
                False,
                "CI_NOT_SUCCESS",
                "repository anchor is not accepted until verified CI status is success",
                repository.repository,
                repository.commit,
                repository.ci_status,
            )

        probe = self._git("rev-parse", "--is-inside-work-tree")
        if probe is None or probe.returncode != 0 or probe.stdout.strip() != "true":
            return RepositoryReconcileResult(
                False,
                "NOT_GIT_WORKTREE",
                "local project is not a readable Git worktree",
                repository.repository,
                repository.commit,
                repository.ci_status,
            )
        head = self._git("rev-parse", "HEAD")
        if head is None or head.returncode != 0:
            return RepositoryReconcileResult(
                False,
                "LOCAL_HEAD_UNAVAILABLE",
                "local Git HEAD could not be resolved",
                repository.repository,
                repository.commit,
                repository.ci_status,
            )
        local_head = head.stdout.strip()
        if local_head != repository.commit:
            return RepositoryReconcileResult(
                False,
                "LOCAL_HEAD_MISMATCH",
                "local HEAD does not match the verified repository-context commit",
                repository.repository,
                repository.commit,
                repository.ci_status,
                local_head,
            )

        dirty = self._business_dirty_paths()
        if dirty is None:
            return RepositoryReconcileResult(
                False,
                "LOCAL_STATUS_UNAVAILABLE",
                "local Git status could not be read",
                repository.repository,
                repository.commit,
                repository.ci_status,
                local_head,
            )
        if dirty:
            return RepositoryReconcileResult(
                False,
                "LOCAL_WORKTREE_DIRTY",
                "business/source files have uncommitted changes; refusing to advance the rolling commit anchor",
                repository.repository,
                repository.commit,
                repository.ci_status,
                local_head,
                dirty,
            )

        rolling = load_rolling_context(self.root)
        updated = replace(
            rolling,
            last_commit=repository.commit,
            updated_at=now_iso(),
        )
        save_rolling_context(self.root, updated)
        self.evidence.record(
            task_id="__repository__",
            kind="REPOSITORY_ANCHOR_ACCEPTED",
            data={
                "repository": repository.repository,
                "branch": repository.branch,
                "commit": repository.commit,
                "ci_status": repository.ci_status,
                "source": repository.source,
                "local_head": local_head,
            },
        )
        return RepositoryReconcileResult(
            True,
            "ACCEPTED",
            "verified repository context, CI and local Git state agree; rolling commit anchor advanced",
            repository.repository,
            repository.commit,
            repository.ci_status,
            local_head,
        )
