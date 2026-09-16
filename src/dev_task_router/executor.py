from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .models import TaskRole
from .router import RoutingDecision


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    task_id: str
    command: list[str] | None
    prompt: str | None
    cwd: Path
    role: TaskRole
    route: RoutingDecision


class Executor(Protocol):
    name: str

    def run(self, request: ExecutionRequest) -> CommandResult: ...


def _run_argv(command: list[str], cwd: Path) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as exc:
        return CommandResult(returncode=127, stdout="", stderr=str(exc))
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class CommandExecutor:
    """Local argv executor. It never invokes a shell."""

    name = "command"

    def run(self, request: ExecutionRequest) -> CommandResult:
        if not request.command:
            return CommandResult(2, "", "command executor requires task.command")
        return _run_argv(request.command, request.cwd)


class AgentCliExecutor:
    """Generic external-agent adapter using an argv template from models.yaml."""

    name = "agent-cli"

    def run(self, request: ExecutionRequest) -> CommandResult:
        template = request.route.profile.command
        if not template:
            return CommandResult(2, "", "agent-cli profile requires a command template")
        if not request.prompt:
            return CommandResult(2, "", "agent-cli executor requires task.prompt")
        values = {
            "model": request.route.profile.model,
            "provider": request.route.profile.provider,
            "prompt": request.prompt,
            "task_id": request.task_id,
            "role": request.role.value,
        }
        try:
            command = [part.format_map(values) for part in template]
        except KeyError as exc:
            return CommandResult(2, "", f"unknown command template placeholder: {exc.args[0]}")
        return _run_argv(command, request.cwd)


class ExecutorRegistry:
    def __init__(self, executors: list[Executor] | None = None):
        items = executors or [CommandExecutor(), AgentCliExecutor()]
        self._executors = {item.name: item for item in items}

    def get(self, name: str) -> Executor:
        try:
            return self._executors[name]
        except KeyError as exc:
            raise ValueError(f"executor not registered: {name}") from exc
