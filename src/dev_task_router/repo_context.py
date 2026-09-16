from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any


_ALLOWED_CI = {"unknown", "pending", "success", "failure", "cancelled"}
_HIGH_RISK_TAGS = {
    "security",
    "auth",
    "authentication",
    "authorization",
    "migration",
    "core-state",
    "public-api",
    "compatibility",
    "persistence",
    "concurrency",
    "data-loss",
}


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"repo context {field_name} must be a string list")
    clean: list[str] = []
    for item in value:
        text = item.strip().replace("\\", "/")
        if not text:
            continue
        if field_name.endswith("files"):
            path = PurePosixPath(text)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"repo context {field_name} contains unsafe path: {item}")
        if text not in clean:
            clean.append(text)
    return tuple(clean)


def _module_key(path_text: str) -> str:
    parts = PurePosixPath(path_text).parts
    if not parts:
        return ""
    if parts[0] in {"src", "app", "apps", "packages", "modules", "lib"} and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


@dataclass(frozen=True, slots=True)
class RepositoryContext:
    repository: str
    branch: str | None = None
    commit: str | None = None
    pr_number: int | None = None
    relevant_files: tuple[str, ...] = ()
    changed_files: tuple[str, ...] = ()
    test_files: tuple[str, ...] = ()
    ci_status: str = "unknown"
    ci_checks: tuple[str, ...] = ()
    evidence_tags: tuple[str, ...] = ()
    facts: tuple[str, ...] = ()
    source: str = "github"
    captured_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RepositoryContext":
        if not isinstance(data, dict):
            raise ValueError("repo context must be a mapping")
        repository = str(data.get("repository", "")).strip()
        if not repository:
            raise ValueError("repo context repository cannot be empty")

        branch_value = data.get("branch")
        commit_value = data.get("commit")
        source = str(data.get("source", "github")).strip() or "github"
        ci_status = str(data.get("ci_status", "unknown")).strip().lower()
        if ci_status not in _ALLOWED_CI:
            raise ValueError(
                "repo context ci_status must be unknown, pending, success, failure or cancelled"
            )

        raw_pr = data.get("pr_number")
        pr_number = None if raw_pr in (None, "") else int(raw_pr)
        if pr_number is not None and pr_number < 1:
            raise ValueError("repo context pr_number must be >= 1")

        return cls(
            repository=repository,
            branch=str(branch_value).strip() if branch_value not in (None, "") else None,
            commit=str(commit_value).strip() if commit_value not in (None, "") else None,
            pr_number=pr_number,
            relevant_files=_string_tuple(data.get("relevant_files"), "relevant_files"),
            changed_files=_string_tuple(data.get("changed_files"), "changed_files"),
            test_files=_string_tuple(data.get("test_files"), "test_files"),
            ci_status=ci_status,
            ci_checks=_string_tuple(data.get("ci_checks"), "ci_checks"),
            evidence_tags=tuple(
                item.lower() for item in _string_tuple(data.get("evidence_tags"), "evidence_tags")
            ),
            facts=_string_tuple(data.get("facts"), "facts"),
            source=source,
            captured_at=(
                str(data.get("captured_at")).strip() if data.get("captured_at") not in (None, "") else None
            ),
        )

    @property
    def all_files(self) -> tuple[str, ...]:
        ordered: list[str] = []
        for path in (*self.relevant_files, *self.changed_files, *self.test_files):
            if path not in ordered:
                ordered.append(path)
        return tuple(ordered)

    @property
    def module_count(self) -> int:
        return len({_module_key(path) for path in self.all_files if _module_key(path)})

    def difficulty_signals(self) -> tuple[int, tuple[str, ...], tuple[str, ...]]:
        """Return a conservative score delta plus explainable repository evidence."""
        delta = 0
        factors: list[str] = []
        traits: set[str] = set()

        scope_files = self.changed_files or self.relevant_files
        file_count = len(scope_files)
        if file_count >= 8:
            delta += 3
            factors.append(f"repo evidence: broad file scope ({file_count}) +3")
            traits.add("broad-scope")
        elif file_count >= 4:
            delta += 2
            factors.append(f"repo evidence: multi-file scope ({file_count}) +2")
            traits.add("multi-file")
        elif file_count >= 2:
            delta += 1
            factors.append(f"repo evidence: related file scope ({file_count}) +1")
            traits.add("multi-file")
        elif file_count == 1:
            factors.append("repo evidence: localized one-file scope +0")
            traits.add("localized")

        modules = self.module_count
        if modules >= 3:
            delta += 2
            factors.append(f"repo evidence: crosses {modules} module roots +2")
            traits.add("cross-module")
        elif modules == 2:
            delta += 1
            factors.append("repo evidence: crosses 2 module roots +1")
            traits.add("cross-module")

        risky = sorted(set(self.evidence_tags) & _HIGH_RISK_TAGS)
        if risky:
            delta += 6
            factors.append(f"repo evidence: high-risk tags {','.join(risky)} +6")
            traits.add("high-risk")

        if self.test_files:
            factors.append(f"repo evidence: {len(self.test_files)} related test file(s) identified +0")
            traits.add("tests-known")
        if self.commit:
            traits.add("commit-anchored")
        if self.pr_number is not None:
            traits.add("pr-context")
        if self.ci_status != "unknown":
            traits.add(f"ci-{self.ci_status}")

        return delta, tuple(factors), tuple(sorted(traits))

    def compact(self, *, max_files: int = 20, max_facts: int = 8) -> dict[str, Any]:
        """Return a context-budgeted representation suitable for handoff/prompt use."""
        if max_files < 1 or max_facts < 0:
            raise ValueError("compact limits must be positive")
        files = self.all_files[:max_files]
        return {
            "source": self.source,
            "repository": self.repository,
            "branch": self.branch,
            "commit": self.commit,
            "pr_number": self.pr_number,
            "ci_status": self.ci_status,
            "ci_checks": list(self.ci_checks[:10]),
            "files": list(files),
            "file_count_total": len(self.all_files),
            "evidence_tags": list(self.evidence_tags),
            "facts": list(self.facts[:max_facts]),
            "captured_at": self.captured_at,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "repository": self.repository,
            "branch": self.branch,
            "commit": self.commit,
            "pr_number": self.pr_number,
            "relevant_files": list(self.relevant_files),
            "changed_files": list(self.changed_files),
            "test_files": list(self.test_files),
            "ci_status": self.ci_status,
            "ci_checks": list(self.ci_checks),
            "evidence_tags": list(self.evidence_tags),
            "facts": list(self.facts),
            "captured_at": self.captured_at,
        }
