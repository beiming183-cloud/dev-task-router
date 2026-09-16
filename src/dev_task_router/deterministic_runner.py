from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .checker import CheckReport, TaskChecker, git_snapshot
from .executor import CommandExecutor, ExecutionRequest
from .handoff import HandoffWriter
from .models import ModelLevel, Plan, TaskSpec, TaskStatus, WorkflowStatus
from .router import RuleRouter
from .state import StateStore, now_iso
from .usage import UsageLogger


@dataclass(frozen=True, slots=True)
class DeterministicRunResult:
    task_id: str
    status: str
    message: str
    check: CheckReport | None = None


class DeterministicTaskRunner:
    """Execute genuine NONE command Tasks without involving a reasoning model.

    A deterministic failure is terminal for this Task invocation and explicitly asks
    for a separate debug Task. It never promotes NONE or retries the same command as a
    model Task, preserving the distinction between command failure and reasoning
    difficulty.
    """

    def __init__(
        self,
        root: Path,
        plan: Plan,
        store: StateStore,
        router: RuleRouter,
        *,
        command_executor: CommandExecutor | None = None,
        checker: TaskChecker | None = None,
    ):
        self.root = root
        self.plan = plan
        self.store = store
        self.router = router
        self.command_executor = command_executor or CommandExecutor()
        self.checker = checker or TaskChecker(self.command_executor)
        self.handoff = HandoffWriter(root)
        self.usage = UsageLogger(root)

    @staticmethod
    def _route_dict(route) -> dict[str, object]:
        return {
            "level": route.level.value,
            "provider": route.profile.provider,
            "model": route.profile.model,
            "executor": route.profile.executor,
            "reason": route.reason,
            "confidence": route.confidence,
            "traits": list(route.traits),
        }

    def run(self, task: TaskSpec) -> DeterministicRunResult:
        state = self.store.ensure_for_plan(self.plan)
        task_state = state["tasks"][task.id]
        if (
            task_state.get("status") in {TaskStatus.FAILED.value, TaskStatus.BLOCKED.value}
            and task_state.get("last_failure_type", "").startswith("DETERMINISTIC")
        ):
            return DeterministicRunResult(
                task.id,
                "DEBUG_TASK_REQUIRED",
                "deterministic Task already failed; create a separate debug Task and classify it independently",
            )

        route = self.router.route(task)
        if route.level != ModelLevel.NONE:
            raise ValueError(f"task {task.id} is not a deterministic NONE task")
        if task.command is None:
            raise ValueError(f"deterministic task {task.id} has no command")

        before_git = git_snapshot(self.root) if task.require_diff else None
        task_state["attempts"] = int(task_state.get("attempts", 0)) + 1
        task_state["started_at"] = now_iso()
        task_state["finished_at"] = None
        task_state["status"] = TaskStatus.RUNNING.value
        task_state["route"] = self._route_dict(route)
        task_state.setdefault("route_history", []).append(
            {"attempt": task_state["attempts"], **self._route_dict(route)}
        )
        state["status"] = WorkflowStatus.RUNNING.value
        state["current_task"] = task.id
        self.store.save(state)

        request = ExecutionRequest(
            task_id=task.id,
            command=task.command,
            prompt=None,
            cwd=self.root,
            role=task.role,
            route=route,
        )
        result = self.command_executor.run(request)
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            return self._fail(task, route, message, "DETERMINISTIC_COMMAND", result.returncode)

        check = self.checker.run(
            task,
            root=self.root,
            route=route,
            before_git=before_git,
        )
        if not check.ok:
            return self._fail(
                task,
                route,
                check.message,
                "DETERMINISTIC_CHECK",
                check.returncode,
                check=check,
            )

        state = self.store.load()
        item = state["tasks"][task.id]
        item["status"] = TaskStatus.PASSED.value
        item["finished_at"] = now_iso()
        item["last_error"] = None
        item["last_failure_type"] = None
        state["current_task"] = None
        all_passed = all(
            state["tasks"][candidate.id]["status"] == TaskStatus.PASSED.value
            for candidate in self.plan.tasks
        )
        state["status"] = WorkflowStatus.PASSED.value if all_passed else WorkflowStatus.READY.value
        self.store.save(state)
        self.handoff.write(self.plan, state)
        self.usage.append(
            task_id=task.id,
            route=self._route_dict(route),
            status="PASSED",
            returncode=0,
        )
        return DeterministicRunResult(task.id, "PASSED", "deterministic command and checks passed", check)

    def _fail(
        self,
        task: TaskSpec,
        route,
        message: str,
        failure_type: str,
        returncode: int | None,
        *,
        check: CheckReport | None = None,
    ) -> DeterministicRunResult:
        state = self.store.load()
        item = state["tasks"][task.id]
        item["status"] = TaskStatus.FAILED.value
        item["finished_at"] = now_iso()
        item["last_error"] = message
        item["last_failure_type"] = failure_type
        item.setdefault("failures", []).append(
            {
                "attempt": item["attempts"],
                "type": failure_type,
                "message": message,
                "route": self._route_dict(route),
                "at": now_iso(),
            }
        )
        item["debug_task_required"] = True
        state["status"] = WorkflowStatus.FAILED.value
        state["current_task"] = task.id
        self.store.save(state)
        self.handoff.write(self.plan, state)
        self.usage.append(
            task_id=task.id,
            route=self._route_dict(route),
            status=f"FAILED_{failure_type}",
            returncode=returncode,
        )
        return DeterministicRunResult(
            task.id,
            "DEBUG_TASK_REQUIRED",
            f"{message}; create a separate debug Task and classify it independently",
            check,
        )
