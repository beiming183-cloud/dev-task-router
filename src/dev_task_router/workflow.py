from __future__ import annotations

from pathlib import Path
from typing import TextIO

from .checker import TaskChecker, git_snapshot
from .config import load_models
from .executor import ExecutionRequest, ExecutorRegistry
from .handoff import HandoffWriter
from .models import Plan, TaskStatus, WorkflowStatus
from .retry import level_for_attempt
from .reviewer import Reviewer
from .router import ModelCatalog, RuleRouter, RoutingDecision
from .state import StateStore, now_iso
from .usage import UsageLogger


class WorkflowEngine:
    def __init__(
        self,
        root: Path,
        plan: Plan,
        store: StateStore,
        catalog: ModelCatalog | None = None,
        registry: ExecutorRegistry | None = None,
        output: TextIO | None = None,
    ):
        import sys

        self.root = root
        self.plan = plan
        self.store = store
        self.catalog = catalog or load_models(root)
        self.router = RuleRouter(self.catalog)
        self.registry = registry or ExecutorRegistry()
        self.command_executor = self.registry.get("command")
        self.checker = TaskChecker(self.command_executor)
        self.reviewer = Reviewer(self.router, self.registry)
        self.output = output or sys.stdout
        self.handoff = HandoffWriter(root)
        self.usage = UsageLogger(root)

    def _print(self, text: str) -> None:
        print(text, file=self.output)

    @staticmethod
    def _route_dict(route: RoutingDecision) -> dict[str, str]:
        return {
            "level": route.level.value,
            "provider": route.profile.provider,
            "model": route.profile.model,
            "executor": route.profile.executor,
            "reason": route.reason,
        }

    def _save(self, state: dict) -> None:
        self.store.save(state)
        self.handoff.write(self.plan, state)

    def run(self) -> dict:
        state = self.store.ensure_for_plan(self.plan)
        self.handoff.write(self.plan, state)
        if state["status"] == WorkflowStatus.PASSED.value:
            self._print("workflow already passed")
            return state
        if state["status"] == WorkflowStatus.PAUSED.value:
            self._print("workflow is paused; use `autodev resume`")
            return state
        if state["status"] in {WorkflowStatus.FAILED.value, WorkflowStatus.BLOCKED.value}:
            self._print("workflow is failed/blocked; use `autodev retry <task>` after inspection")
            return state

        state["status"] = WorkflowStatus.RUNNING.value
        self._save(state)

        for task in self.plan.tasks:
            state = self.store.load()
            if state["status"] == WorkflowStatus.PAUSED.value:
                self._print("workflow paused")
                self.handoff.write(self.plan, state)
                return state

            task_state = state["tasks"][task.id]
            if task_state["status"] == TaskStatus.PASSED.value:
                continue

            result_state = self._run_task(task)
            if result_state["tasks"][task.id]["status"] != TaskStatus.PASSED.value:
                return result_state

        state = self.store.load()
        state["status"] = WorkflowStatus.PASSED.value
        state["current_task"] = None
        self._save(state)
        self._print("workflow PASSED")
        return state

    def _run_task(self, task) -> dict:
        base_route = self.router.route(task)

        while True:
            state = self.store.load()
            task_state = state["tasks"][task.id]
            next_attempt = task_state["attempts"] + 1
            if next_attempt > task.max_attempts:
                return self._terminal_failure(
                    task,
                    task_state.get("last_error") or "retry budget exhausted",
                    task_state.get("last_failure_type") or "RETRY",
                )

            effective_level = level_for_attempt(
                base_route.level,
                next_attempt,
                task.escalate_after,
            )
            if effective_level == base_route.level:
                route = self.router.route(task)
            else:
                route = self.router.route(
                    task,
                    override_level=effective_level,
                    override_reason=(
                        f"retry escalation attempt {next_attempt}: "
                        f"{base_route.level.value}->{effective_level.value}"
                    ),
                )
            route_data = self._route_dict(route)

            state["current_task"] = task.id
            state["status"] = WorkflowStatus.RUNNING.value
            task_state["status"] = TaskStatus.RUNNING.value
            task_state["attempts"] = next_attempt
            task_state["started_at"] = now_iso()
            task_state["finished_at"] = None
            task_state["last_error"] = None
            task_state["last_failure_type"] = None
            task_state["route"] = route_data
            task_state.setdefault("route_history", []).append(
                {"attempt": next_attempt, **route_data}
            )
            self._save(state)

            self._print(
                f"[{task.role.value}/{route.level.value}] {task.stage_id}/{task.step_id}/{task.id}: "
                f"attempt {next_attempt}/{task.max_attempts} -> "
                f"{route.profile.provider}:{route.profile.model} via {route.profile.executor}"
            )

            before_git = git_snapshot(self.root) if task.require_diff else None
            try:
                executor = self.registry.get(route.profile.executor)
            except ValueError as exc:
                if self._record_failure(task, str(exc), "EXECUTOR", route_data, None):
                    return self.store.load()
                continue

            request = ExecutionRequest(
                task_id=task.id,
                command=task.command,
                prompt=task.prompt,
                cwd=self.root,
                role=task.role,
                route=route,
            )
            result = executor.run(request)
            if result.stdout.strip():
                self._print(result.stdout.rstrip())
            if result.returncode != 0:
                message = result.stderr.strip() or f"exit code {result.returncode}"
                if self._record_failure(task, message, "EXECUTOR", route_data, result.returncode):
                    return self.store.load()
                continue

            check = self.checker.run(
                task,
                root=self.root,
                route=route,
                before_git=before_git,
            )
            if check.evidence.strip():
                self._print(check.evidence.rstrip())
            if not check.ok:
                if self._record_failure(
                    task,
                    check.message,
                    check.failure_type or "CHECK",
                    route_data,
                    check.returncode,
                ):
                    return self.store.load()
                continue

            if task.review:
                review = self.reviewer.review(
                    task,
                    root=self.root,
                    checker_evidence=check.evidence,
                )
                state = self.store.load()
                state["tasks"][task.id]["review"] = {
                    "ok": review.ok,
                    "message": review.message,
                    "raw": review.raw,
                    "level": task.review_level.value,
                }
                self._save(state)
                if not review.ok:
                    if self._record_failure(
                        task,
                        review.message,
                        "REVIEW",
                        route_data,
                        review.returncode,
                    ):
                        return self.store.load()
                    continue

            state = self.store.load()
            task_state = state["tasks"][task.id]
            task_state["status"] = TaskStatus.PASSED.value
            task_state["finished_at"] = now_iso()
            task_state["last_error"] = None
            task_state["last_failure_type"] = None
            state["current_task"] = None
            self._save(state)
            self.usage.append(task_id=task.id, route=route_data, status="PASSED", returncode=0)
            self._print(f"PASS {task.id}")
            return state

    def _record_failure(
        self,
        task,
        message: str,
        failure_type: str,
        route: dict,
        returncode: int | None,
    ) -> bool:
        state = self.store.load()
        task_state = state["tasks"][task.id]
        clean_message = message.strip()
        task_state["status"] = TaskStatus.FAILED.value
        task_state["finished_at"] = now_iso()
        task_state["last_error"] = clean_message
        task_state["last_failure_type"] = failure_type
        task_state.setdefault("failures", []).append(
            {
                "attempt": task_state["attempts"],
                "type": failure_type,
                "message": clean_message,
                "route": route,
                "at": now_iso(),
            }
        )
        self.usage.append(
            task_id=task.id,
            route=route,
            status=f"FAILED_{failure_type}",
            returncode=returncode,
        )

        exhausted = task_state["attempts"] >= task.max_attempts
        if exhausted:
            terminal = TaskStatus.BLOCKED.value if task.max_attempts > 1 else TaskStatus.FAILED.value
            workflow_terminal = (
                WorkflowStatus.BLOCKED.value if task.max_attempts > 1 else WorkflowStatus.FAILED.value
            )
            task_state["status"] = terminal
            state["status"] = workflow_terminal
            state["current_task"] = task.id
            self._save(state)
            self._print(f"{terminal} {task.id}: {clean_message}")
            return True

        state["status"] = WorkflowStatus.RUNNING.value
        self._save(state)
        self._print(
            f"RETRY {task.id}: {failure_type} failed on attempt {task_state['attempts']}; "
            f"{task.max_attempts - task_state['attempts']} attempt(s) left"
        )
        return False

    def _terminal_failure(self, task, message: str, failure_type: str) -> dict:
        state = self.store.load()
        item = state["tasks"][task.id]
        item["status"] = TaskStatus.BLOCKED.value
        item["last_error"] = message
        item["last_failure_type"] = failure_type
        item["finished_at"] = now_iso()
        state["status"] = WorkflowStatus.BLOCKED.value
        state["current_task"] = task.id
        self._save(state)
        self._print(f"BLOCKED {task.id}: {message}")
        return state
