from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkflowStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    PASSED = "PASSED"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    PASSED = "PASSED"


class ModelLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class TaskRole(str, Enum):
    PLANNER = "PLANNER"
    EXECUTOR = "EXECUTOR"
    REVIEWER = "REVIEWER"


@dataclass(slots=True)
class TaskSpec:
    id: str
    title: str
    command: list[str] | None = None
    prompt: str | None = None
    kind: str = "normal_code"
    level: ModelLevel | None = None
    role: TaskRole = TaskRole.EXECUTOR
    checks: list[list[str]] = field(default_factory=list)
    acceptance: list[str] = field(default_factory=list)
    require_diff: bool = False
    max_attempts: int = 1
    escalate_after: int = 2
    review: bool = False
    review_level: ModelLevel = ModelLevel.HIGH
    stage_id: str = "default"
    step_id: str = "default"

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        stage_id: str = "default",
        step_id: str = "default",
    ) -> "TaskSpec":
        if not isinstance(data, dict):
            raise ValueError("every task must be a mapping")
        task_id = str(data.get("id", "")).strip()
        title = str(data.get("title", task_id)).strip()
        command = data.get("command")
        prompt_value = data.get("prompt")
        prompt = str(prompt_value).strip() if prompt_value is not None else None
        kind = str(data.get("kind", "normal_code")).strip().lower()
        raw_level = data.get("level", data.get("model"))
        raw_role = str(data.get("role", "EXECUTOR")).strip().upper()
        checks = data.get("checks", [])
        acceptance = data.get("acceptance", [])
        require_diff = bool(data.get("require_diff", False))
        max_attempts = int(data.get("max_attempts", 1))
        escalate_after = int(data.get("escalate_after", 2))
        review = bool(data.get("review", False))
        raw_review_level = str(data.get("review_level", "HIGH")).strip().upper()

        if not task_id:
            raise ValueError("task.id cannot be empty")
        if not title:
            raise ValueError(f"task {task_id}: title cannot be empty")
        if not kind:
            raise ValueError(f"task {task_id}: kind cannot be empty")
        if command is not None and (
            not isinstance(command, list)
            or not command
            or not all(isinstance(x, str) for x in command)
        ):
            raise ValueError(f"task {task_id}: command must be a non-empty string list when provided")
        if command is None and not prompt:
            raise ValueError(f"task {task_id}: provide command or prompt")
        if not isinstance(checks, list):
            raise ValueError(f"task {task_id}: checks must be a list")
        if not isinstance(acceptance, list) or not all(isinstance(x, str) for x in acceptance):
            raise ValueError(f"task {task_id}: acceptance must be a string list")
        if max_attempts < 1:
            raise ValueError(f"task {task_id}: max_attempts must be >= 1")
        if escalate_after < 1:
            raise ValueError(f"task {task_id}: escalate_after must be >= 1")

        normalized_checks: list[list[str]] = []
        for check in checks:
            if not isinstance(check, list) or not check or not all(isinstance(x, str) for x in check):
                raise ValueError(f"task {task_id}: every check must be a non-empty string list")
            normalized_checks.append(check)

        level: ModelLevel | None = None
        if raw_level is not None:
            try:
                level = ModelLevel(str(raw_level).strip().upper())
            except ValueError as exc:
                raise ValueError(
                    f"task {task_id}: level/model must be one of NONE, LOW, MEDIUM, HIGH"
                ) from exc
        try:
            role = TaskRole(raw_role)
        except ValueError as exc:
            raise ValueError(f"task {task_id}: role must be PLANNER, EXECUTOR or REVIEWER") from exc
        try:
            review_level = ModelLevel(raw_review_level)
        except ValueError as exc:
            raise ValueError(f"task {task_id}: review_level must be NONE, LOW, MEDIUM or HIGH") from exc

        return cls(
            id=task_id,
            title=title,
            command=command,
            prompt=prompt,
            kind=kind,
            level=level,
            role=role,
            checks=normalized_checks,
            acceptance=[item.strip() for item in acceptance if item.strip()],
            require_diff=require_diff,
            max_attempts=max_attempts,
            escalate_after=escalate_after,
            review=review,
            review_level=review_level,
            stage_id=stage_id,
            step_id=step_id,
        )


@dataclass(slots=True)
class StepSpec:
    id: str
    title: str
    tasks: list[TaskSpec]

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, stage_id: str) -> "StepSpec":
        if not isinstance(data, dict):
            raise ValueError("every step must be a mapping")
        step_id = str(data.get("id", "")).strip()
        title = str(data.get("title", step_id)).strip()
        raw_tasks = data.get("tasks")
        if not step_id:
            raise ValueError(f"stage {stage_id}: step.id cannot be empty")
        if not isinstance(raw_tasks, list) or not raw_tasks:
            raise ValueError(f"step {step_id}: tasks must contain at least one task")
        tasks = [
            TaskSpec.from_dict(item, stage_id=stage_id, step_id=step_id)
            for item in raw_tasks
        ]
        return cls(id=step_id, title=title, tasks=tasks)


@dataclass(slots=True)
class StageSpec:
    id: str
    title: str
    steps: list[StepSpec]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StageSpec":
        if not isinstance(data, dict):
            raise ValueError("every stage must be a mapping")
        stage_id = str(data.get("id", "")).strip()
        title = str(data.get("title", stage_id)).strip()
        raw_steps = data.get("steps")
        if not stage_id:
            raise ValueError("stage.id cannot be empty")
        if not isinstance(raw_steps, list) or not raw_steps:
            raise ValueError(f"stage {stage_id}: steps must contain at least one step")
        steps = [StepSpec.from_dict(item, stage_id=stage_id) for item in raw_steps]
        return cls(id=stage_id, title=title, steps=steps)


@dataclass(slots=True)
class Plan:
    project: str
    tasks: list[TaskSpec]
    stages: list[StageSpec] = field(default_factory=list)
    version: int = 3

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        project = str(data.get("project", "")).strip()
        if not project:
            raise ValueError("plan.project cannot be empty")

        version = int(data.get("version", 1))
        raw_stages = data.get("stages")
        raw_tasks = data.get("tasks")

        stages: list[StageSpec] = []
        if raw_stages is not None:
            if not isinstance(raw_stages, list) or not raw_stages:
                raise ValueError("plan.stages must contain at least one stage")
            stages = [StageSpec.from_dict(item) for item in raw_stages]
            tasks = [task for stage in stages for step in stage.steps for task in step.tasks]
        else:
            if not isinstance(raw_tasks, list) or not raw_tasks:
                raise ValueError("plan.tasks must contain at least one task")
            tasks = [TaskSpec.from_dict(item) for item in raw_tasks]

        ids = [task.id for task in tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("task ids must be unique across the whole plan")

        return cls(project=project, tasks=tasks, stages=stages, version=version)
