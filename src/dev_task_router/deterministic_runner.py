from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from .checker import CheckReport, TaskChecker, git_snapshot, snapshot_digest
from .debug_task import DebugTaskMaterializer
from .execution_evidence import ExecutionEvidenceLedger
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
        evidence: ExecutionEvidenceLedger | None = None,
    ):
        self.root = root
        self.plan = plan
        self.store = store
        self.router = router
        self.command_executor = command_executor or CommandExecutor()
        self.checker = checker or TaskChecker(self.command_executor)
        self.handoff = HandoffWriter(root)
        self.usage = UsageLogger(root)
        self.evidence = evidence or ExecutionEvidenceLedger(root)

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

    @staticmethod
    def _command_digest(command: list[str]) -> str:
        payload = json.dumps(command, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _record_state(self, task: TaskSpec, *, status: str) -> None:
        state = self.store.load()
        item = state["tasks"][task.id]
        self.evidence.record(
            task_id=task.id,
            kind="STATE_RECORDED",
            data={
                "execution": "deterministic",
                "task_status": item.get("status"),
                "attempts": item.get("attempts"),
                "last_failure_type": item.get("last_failure_type"),
                "workflow_status": state.get("status"),
                "result_status": status,
            },
        )

    def run(self, task: TaskSpec) -> DeterministicRunResult:
        state = self.store.ensure_for_plan(self.plan)
        task_state = state["tasks"][task.id]
        if (
            task_state.get("status") in {TaskStatus.FAILED.value, TaskStatus.BLOCKED.value}
            and task_state.get("last_failure_type", "").startswith("DETERMINISTIC")
        ):
            debug_file = task_state.get("debug_task_file")
            suffix = f"; candidate: {debug_file}" if debug_file else ""
            return DeterministicRunResult(
                task.id,
                "DEBUG_TASK_REQUIRED",
                "deterministic Task already failed; use the separate debug Task and classify it independently"
                + suffix,
            )

        route = self.router.route(task)
        if route.level != ModelLevel.NONE:
            raise ValueError(f"task {task.id} is not a deterministic NONE task")
        if task.command is None:
            raise ValueError(f"deterministic task {task.id} has no command")

        before_git = git_snapshot(self.root) if task.require_diff else None
        before_git_digest = snapshot_digest(before_git) if before_git is not None else None
        task_state["attempts"] = int(task_state.get("attempts", 0)) + 1
        attempt = int(task_state["attempts"])
        task_state["started_at"] = now_iso()
        task_state["finished_at"] = None
        task_state["status"] = TaskStatus.RUNNING.value
        task_state["route"] = self._route_dict(route)
        task_state.setdefault("route_history", []).append(
            {"attempt": attempt, **self._route_dict(route)}
        )
        state["status"] = WorkflowStatus.RUNNING.value
        state["current_task"] = task.id
        self.store.save(state)

        self.evidence.record(
            task_id=task.id,
            kind="DETERMINISTIC_STARTED",
            data={
                "attempt": attempt,
                "level": ModelLevel.NONE.value,
                "command_digest": self._command_digest(task.command),
                "argv_count": len(task.command),
                "require_diff": task.require_diff,
                "before_git_digest": before_git_digest,
            },
        )

        total_started = time.monotonic()
        command_started = time.monotonic()
        request = ExecutionRequest(
            task_id=task.id,
            command=task.command,
            prompt=None,
            cwd=self.root,
            role=task.role,
            route=route,
        )
        result = self.command_executor.run(request)
        command_duration = time.monotonic() - command_started
        self.evidence.record(
            task_id=task.id,
            kind="DETERMINISTIC_COMMAND_COMPLETED",
            data={
                "attempt": attempt,
                "returncode": result.returncode,
                "ok": result.returncode == 0,
                "duration_seconds": round(command_duration, 6),
            },
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            outcome = self._fail(
                task,
                route,
                message,
                "DETERMINISTIC_COMMAND",
                result.returncode,
                duration_seconds=time.monotonic() - total_started,
            )
            self._record_state(task, status=outcome.status)
            return outcome

        check = self.checker.run(
            task,
            root=self.root,
            route=route,
            before_git=before_git,
        )
        total_duration = time.monotonic() - total_started
        self.evidence.record(
            task_id=task.id,
            kind="DETERMINISTIC_CHECKED",
            data={
                "attempt": attempt,
                "ok": check.ok,
                "failure_type": check.failure_type,
                "returncode": check.returncode,
                "message": check.message,
                "duration_seconds": round(total_duration, 6),
            },
        )
        if not check.ok:
            outcome = self._fail(
                task,
                route,
                check.message,
                "DETERMINISTIC_CHECK",
                check.returncode,
                check=check,
                duration_seconds=total_duration,
            )
            self._record_state(task, status=outcome.status)
            return outcome

        state = self.store.load()
        item = state["tasks"][task.id]
        item["status"] = TaskStatus.PASSED.value
        item["finished_at"] = now_iso()
        item["last_error"] = None
        item["last_failure_type"] = None
        item["debug_task_recheck_pending"] = False
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
            attempt=attempt,
            duration_seconds=total_duration,
            source="deterministic",
            usage_id=f"deterministic:{task.id}:attempt:{attempt}",
        )
        outcome = DeterministicRunResult(
            task.id,
            "PASSED",
            "deterministic command and checks passed",
            check,
        )
        self._record_state(task, status=outcome.status)
        return outcome

    def _fail(
        self,
        task: TaskSpec,
        route,
        message: str,
        failure_type: str,
        returncode: int | None,
        *,
        check: CheckReport | None = None,
        duration_seconds: float | None = None,
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

        debug_note = ""
        try:
            candidate = DebugTaskMaterializer(self.root, self.plan, self.store).materialize(task.id)
            relative = candidate.path.relative_to(self.root).as_posix()
            debug_note = f"; debug Task candidate materialized at {relative}"
            state = self.store.load()
            self.evidence.record(
                task_id=task.id,
                kind="DEBUG_TASK_MATERIALIZED",
                data={
                    "source_failure_type": failure_type,
                    "debug_task_id": candidate.debug_task_id,
                    "path": relative,
                    "auto_execute": False,
                },
            )
        except (OSError, ValueError) as exc:
            debug_note = f"; debug Task candidate could not be materialized: {exc}"
            state = self.store.load()

        self.handoff.write(self.plan, state)
        attempt = int(item.get("attempts", 0))
        self.usage.append(
            task_id=task.id,
            route=self._route_dict(route),
            status=f"FAILED_{failure_type}",
            returncode=returncode,
            attempt=attempt,
            failure_type=failure_type,
            duration_seconds=duration_seconds,
            source="deterministic",
            usage_id=f"deterministic:{task.id}:attempt:{attempt}",
        )
        return DeterministicRunResult(
            task.id,
            "DEBUG_TASK_REQUIRED",
            f"{message}{debug_note}; classify the separate debug Task independently before execution",
            check,
        )
