from __future__ import annotations

from pathlib import Path
from typing import TextIO

from .config import load_models
from .executor import ExecutionRequest, ExecutorRegistry
from .handoff import HandoffWriter
from .models import Plan, TaskStatus, WorkflowStatus
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

            route = self.router.route(task)
            route_data = self._route_dict(route)
            state["current_task"] = task.id
            task_state["status"] = TaskStatus.RUNNING.value
            task_state["attempts"] += 1
            task_state["started_at"] = now_iso()
            task_state["finished_at"] = None
            task_state["last_error"] = None
            task_state["route"] = route_data
            self._save(state)

            self._print(
                f"[{task.role.value}/{route.level.value}] {task.stage_id}/{task.step_id}/{task.id}: "
                f"{task.title} -> {route.profile.provider}:{route.profile.model} "
                f"via {route.profile.executor}"
            )
            try:
                executor = self.registry.get(route.profile.executor)
            except ValueError as exc:
                return self._fail(task.id, str(exc), route_data, None)

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
                return self._fail(
                    task.id,
                    result.stderr or f"exit code {result.returncode}",
                    route_data,
                    result.returncode,
                )

            for check in task.checks:
                check_request = ExecutionRequest(
                    task_id=f"{task.id}:check",
                    command=check,
                    prompt=None,
                    cwd=self.root,
                    role=task.role,
                    route=route,
                )
                check_result = self.command_executor.run(check_request)
                if check_result.stdout.strip():
                    self._print(check_result.stdout.rstrip())
                if check_result.returncode != 0:
                    return self._fail(
                        task.id,
                        check_result.stderr or f"check exit code {check_result.returncode}",
                        route_data,
                        check_result.returncode,
                    )

            state = self.store.load()
            task_state = state["tasks"][task.id]
            task_state["status"] = TaskStatus.PASSED.value
            task_state["finished_at"] = now_iso()
            task_state["last_error"] = None
            state["current_task"] = None
            self._save(state)
            self.usage.append(task_id=task.id, route=route_data, status="PASSED", returncode=0)
            self._print(f"PASS {task.id}")

        state = self.store.load()
        state["status"] = WorkflowStatus.PASSED.value
        state["current_task"] = None
        self._save(state)
        self._print("workflow PASSED")
        return state

    def _fail(self, task_id: str, message: str, route: dict, returncode: int | None) -> dict:
        state = self.store.load()
        task_state = state["tasks"][task_id]
        task_state["status"] = TaskStatus.FAILED.value
        task_state["finished_at"] = now_iso()
        task_state["last_error"] = message.strip()
        state["status"] = WorkflowStatus.FAILED.value
        state["current_task"] = task_id
        self._save(state)
        self.usage.append(task_id=task_id, route=route, status="FAILED", returncode=returncode)
        self._print(f"FAIL {task_id}: {task_state['last_error']}")
        return state
