from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from .models import Plan, TaskSpec
from .repo_context import RepositoryContext


def _unique_strings(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"rolling context {field_name} must be a string list")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = " ".join(item.strip().split())
        if not text:
            continue
        key = text.casefold()
        if key not in seen:
            seen.add(key)
            result.append(text)
    return tuple(result)


def _append_unique(values: tuple[str, ...], note: str) -> tuple[str, ...]:
    text = " ".join(note.strip().split())
    if not text:
        return values
    key = text.casefold()
    if any(item.casefold() == key for item in values):
        return values
    return (*values, text)


def _notes_map(value: Any, field_name: str) -> dict[str, tuple[str, ...]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"rolling context {field_name} must be a mapping")
    result: dict[str, tuple[str, ...]] = {}
    for raw_key, raw_notes in value.items():
        key = str(raw_key).strip()
        if not key:
            raise ValueError(f"rolling context {field_name} contains an empty key")
        result[key] = _unique_strings(raw_notes, f"{field_name}.{key}")
    return result


@dataclass(frozen=True, slots=True)
class ContextBudget:
    max_decisions: int = 8
    max_constraints: int = 8
    max_stage_notes: int = 6
    max_task_notes: int = 6
    max_repo_files: int = 12
    max_repo_facts: int = 6
    max_failures: int = 3
    max_acceptance: int = 6

    def __post_init__(self) -> None:
        for name in (
            "max_decisions",
            "max_constraints",
            "max_stage_notes",
            "max_task_notes",
            "max_repo_files",
            "max_repo_facts",
            "max_failures",
            "max_acceptance",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"context budget {name} must be >= 0")


@dataclass(frozen=True, slots=True)
class RollingProjectContext:
    project: str
    goal: str = ""
    decisions: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    stage_notes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    task_notes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    last_commit: str | None = None
    updated_at: str | None = None
    version: int = 1

    @classmethod
    def empty(cls, project: str) -> "RollingProjectContext":
        name = project.strip()
        if not name:
            raise ValueError("rolling context project cannot be empty")
        return cls(project=name)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RollingProjectContext":
        if not isinstance(data, dict):
            raise ValueError("rolling context must be a mapping")
        project = str(data.get("project", "")).strip()
        if not project:
            raise ValueError("rolling context project cannot be empty")
        goal = " ".join(str(data.get("goal", "")).strip().split())
        commit_value = data.get("last_commit")
        updated_value = data.get("updated_at")
        return cls(
            project=project,
            goal=goal,
            decisions=_unique_strings(data.get("decisions"), "decisions"),
            constraints=_unique_strings(data.get("constraints"), "constraints"),
            stage_notes=_notes_map(data.get("stage_notes"), "stage_notes"),
            task_notes=_notes_map(data.get("task_notes"), "task_notes"),
            last_commit=(
                str(commit_value).strip() if commit_value not in (None, "") else None
            ),
            updated_at=(
                str(updated_value).strip() if updated_value not in (None, "") else None
            ),
            version=int(data.get("version", 1)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "project": self.project,
            "goal": self.goal,
            "decisions": list(self.decisions),
            "constraints": list(self.constraints),
            "stage_notes": {key: list(value) for key, value in self.stage_notes.items()},
            "task_notes": {key: list(value) for key, value in self.task_notes.items()},
            "last_commit": self.last_commit,
            "updated_at": self.updated_at,
        }

    @property
    def item_count(self) -> int:
        return (
            len(self.decisions)
            + len(self.constraints)
            + sum(len(value) for value in self.stage_notes.values())
            + sum(len(value) for value in self.task_notes.values())
        )

    def is_stale_against(self, repository: RepositoryContext | None) -> bool:
        return bool(
            self.last_commit
            and repository is not None
            and repository.commit
            and self.last_commit != repository.commit
        )

    def with_task_note(
        self,
        task_id: str,
        note: str,
        *,
        updated_at: str | None = None,
    ) -> "RollingProjectContext":
        key = task_id.strip()
        if not key:
            raise ValueError("rolling context task note requires a task id")
        notes = dict(self.task_notes)
        notes[key] = _append_unique(notes.get(key, ()), note)
        return replace(
            self,
            task_notes=notes,
            updated_at=updated_at if updated_at is not None else self.updated_at,
        )

    def with_stage_note(
        self,
        stage_id: str,
        note: str,
        *,
        updated_at: str | None = None,
    ) -> "RollingProjectContext":
        key = stage_id.strip()
        if not key:
            raise ValueError("rolling context stage note requires a stage id")
        notes = dict(self.stage_notes)
        notes[key] = _append_unique(notes.get(key, ()), note)
        return replace(
            self,
            stage_notes=notes,
            updated_at=updated_at if updated_at is not None else self.updated_at,
        )


@dataclass(frozen=True, slots=True)
class TaskContextPack:
    project: str
    stage: str
    step: str
    task_id: str
    task_title: str
    goal: str
    decisions: tuple[str, ...]
    constraints: tuple[str, ...]
    stage_notes: tuple[str, ...]
    task_notes: tuple[str, ...]
    acceptance: tuple[str, ...]
    failures: tuple[str, ...]
    repository: dict[str, Any] | None
    requested_route: dict[str, Any] | None
    next_action: str
    stale_context: bool
    omitted: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "project": self.project,
            "stage": self.stage,
            "step": self.step,
            "task_id": self.task_id,
            "task_title": self.task_title,
            "goal": self.goal,
            "decisions": list(self.decisions),
            "constraints": list(self.constraints),
            "stage_notes": list(self.stage_notes),
            "task_notes": list(self.task_notes),
            "acceptance": list(self.acceptance),
            "failures": list(self.failures),
            "repository": self.repository,
            "requested_route": self.requested_route,
            "next_action": self.next_action,
            "stale_context": self.stale_context,
            "omitted": dict(self.omitted),
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Task Context Pack — {self.task_id}",
            "",
            f"- Project: `{self.project}`",
            f"- Stage / Step: `{self.stage}` / `{self.step}`",
            f"- Task: `{self.task_title}`",
            f"- Stale context: `{'yes' if self.stale_context else 'no'}`",
        ]
        if self.goal:
            lines.extend(["", "## Project goal", "", self.goal])
        for heading, values in (
            ("Decisions that still apply", self.decisions),
            ("Protected constraints", self.constraints),
            ("Current stage context", self.stage_notes),
            ("Task-specific context", self.task_notes),
            ("Acceptance", self.acceptance),
            ("Recent failure evidence", self.failures),
        ):
            if values:
                lines.extend(["", f"## {heading}", ""])
                lines.extend(f"- {value}" for value in values)

        if self.repository:
            repo = self.repository
            lines.extend(
                [
                    "",
                    "## Repository evidence",
                    "",
                    f"- Repository: `{repo['repository']}`",
                    f"- Branch: `{repo.get('branch') or 'unknown'}`",
                    f"- Commit: `{repo.get('commit') or 'unanchored'}`",
                    f"- CI: `{repo.get('ci_status') or 'unknown'}`",
                ]
            )
            if repo.get("files"):
                lines.append("- Relevant files:")
                lines.extend(f"  - `{path}`" for path in repo["files"])
            if repo.get("facts"):
                lines.append("- Verified facts:")
                lines.extend(f"  - {fact}" for fact in repo["facts"])

        if self.requested_route:
            route = self.requested_route
            lines.extend(
                [
                    "",
                    "## Requested execution profile",
                    "",
                    f"- Difficulty: `{route.get('level') or 'unknown'}`",
                    f"- Model: `{route.get('model') or 'unresolved'}`",
                    f"- Executor: `{route.get('executor') or 'unresolved'}`",
                ]
            )

        lines.extend(["", "## Exact next action", "", self.next_action or self.task_title])
        omitted_total = sum(self.omitted.values())
        if omitted_total:
            lines.extend(
                [
                    "",
                    "## Context budget",
                    "",
                    f"- {omitted_total} older/non-essential item(s) omitted by budget.",
                ]
            )
        if self.stale_context:
            lines.extend(
                [
                    "",
                    "> Rolling context was anchored to an older commit. Refresh commit-sensitive facts before implementation.",
                ]
            )
        return "\n".join(lines) + "\n"


class ContextPackBuilder:
    def __init__(self, budget: ContextBudget | None = None):
        self.budget = budget or ContextBudget()

    @staticmethod
    def _take(values: tuple[str, ...] | list[str], limit: int) -> tuple[tuple[str, ...], int]:
        clean = tuple(values)
        if limit == 0:
            return (), len(clean)
        selected = clean[-limit:]
        return selected, max(0, len(clean) - len(selected))

    def build(
        self,
        plan: Plan,
        state: dict[str, Any],
        task: TaskSpec,
        rolling: RollingProjectContext,
        repository: RepositoryContext | None = None,
        requested_route: dict[str, Any] | None = None,
    ) -> TaskContextPack:
        if rolling.project != plan.project:
            raise ValueError("rolling context project does not match plan project")
        if task.id not in state.get("tasks", {}):
            raise ValueError(f"task {task.id} is missing from workflow state")

        decisions, omitted_decisions = self._take(rolling.decisions, self.budget.max_decisions)
        constraints, omitted_constraints = self._take(
            rolling.constraints, self.budget.max_constraints
        )
        stage_values = rolling.stage_notes.get(task.stage_id, ())
        stage_notes, omitted_stage = self._take(stage_values, self.budget.max_stage_notes)
        task_values = rolling.task_notes.get(task.id, ())
        task_notes, omitted_task = self._take(task_values, self.budget.max_task_notes)
        acceptance, omitted_acceptance = self._take(
            task.acceptance, self.budget.max_acceptance
        )

        item = state["tasks"][task.id]
        raw_failures: list[str] = []
        for failure in item.get("failures", []):
            if isinstance(failure, dict):
                kind = str(failure.get("type") or failure.get("failure_type") or "failure")
                message = str(failure.get("message") or failure.get("error") or "").strip()
                raw_failures.append(f"{kind}: {message}" if message else kind)
            elif failure:
                raw_failures.append(str(failure))
        if item.get("last_error") and not raw_failures:
            kind = str(item.get("last_failure_type") or "failure")
            raw_failures.append(f"{kind}: {item['last_error']}")
        failures, omitted_failures = self._take(raw_failures, self.budget.max_failures)

        repo_compact = None
        if repository is not None:
            repo_compact = repository.compact(
                max_files=max(1, self.budget.max_repo_files),
                max_facts=self.budget.max_repo_facts,
            )
            if self.budget.max_repo_files == 0:
                repo_compact["files"] = []

        route = requested_route or item.get("route")
        next_action = (task.prompt or task.title).strip()
        if len(next_action) > 800:
            next_action = next_action[:797] + "..."

        return TaskContextPack(
            project=plan.project,
            stage=task.stage_id,
            step=task.step_id,
            task_id=task.id,
            task_title=task.title,
            goal=rolling.goal,
            decisions=decisions,
            constraints=constraints,
            stage_notes=stage_notes,
            task_notes=task_notes,
            acceptance=acceptance,
            failures=failures,
            repository=repo_compact,
            requested_route=route,
            next_action=next_action,
            stale_context=rolling.is_stale_against(repository),
            omitted={
                "decisions": omitted_decisions,
                "constraints": omitted_constraints,
                "stage_notes": omitted_stage,
                "task_notes": omitted_task,
                "acceptance": omitted_acceptance,
                "failures": omitted_failures,
            },
        )
