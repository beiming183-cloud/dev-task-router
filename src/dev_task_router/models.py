from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    PASSED = "PASSED"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    PASSED = "PASSED"


@dataclass(slots=True)
class TaskSpec:
    id: str
    title: str
    command: list[str]
    model: str = "NONE"
    checks: list[list[str]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskSpec":
        task_id = str(data.get("id", "")).strip()
        title = str(data.get("title", task_id)).strip()
        command = data.get("command")
        model = str(data.get("model", "NONE")).upper()
        checks = data.get("checks", [])

        if not task_id:
            raise ValueError("task.id cannot be empty")
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            raise ValueError(f"task {task_id}: command must be a non-empty string list")
        if not isinstance(checks, list):
            raise ValueError(f"task {task_id}: checks must be a list")

        normalized_checks: list[list[str]] = []
        for check in checks:
            if not isinstance(check, list) or not check or not all(isinstance(x, str) for x in check):
                raise ValueError(f"task {task_id}: every check must be a non-empty string list")
            normalized_checks.append(check)

        return cls(id=task_id, title=title, command=command, model=model, checks=normalized_checks)


@dataclass(slots=True)
class Plan:
    project: str
    tasks: list[TaskSpec]
    version: int = 1

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        project = str(data.get("project", "")).strip()
        if not project:
            raise ValueError("plan.project cannot be empty")

        raw_tasks = data.get("tasks")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise ValueError("plan.tasks must contain at least one task")

        tasks = [TaskSpec.from_dict(item) for item in raw_tasks]
        ids = [task.id for task in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task ids must be unique")

        return cls(project=project, tasks=tasks, version=int(data.get("version", 1)))
