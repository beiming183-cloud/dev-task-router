from __future__ import annotations

from pathlib import Path
from typing import TextIO

from .executor import CommandExecutor
from .models import Plan, TaskStatus, WorkflowStatus
from .state import StateStore, now_iso


class WorkflowEngine:
    def __init__(
        self,
        root: Path,
        plan: Plan,
        store: StateStore,
        executor: CommandExecutor | None = None,
        output: TextIO | None = None,
    ):
        import sys

        self.root = root
        self.plan = plan
        self.store = store
        self.executor = executor or CommandExecutor()
        self.output = output or sys.stdout

    def _print(self, text: str) -> None:
        print(text, file=self.output)

    def run(self) -> dict:
        state = self.store.ensure_for_plan(self.plan)
        if state["status"] == WorkflowStatus.PASSED.value:
            self._print("workflow already passed")
            return state
        if state["status"] == WorkflowStatus.PAUSED.value:
            self._print("workflow is paused; use `autodev resume`")
            return state

        state["status"] = WorkflowStatus.RUNNING.value
        self.store.save(state)

        for task in self.plan.tasks:
            # Reload before every task so another process can pause the workflow.
            state = self.store.load()
            if state["status"] == WorkflowStatus.PAUSED.value:
                self._print("workflow paused")
                return state

            task_state = state["tasks"][task.id]
            if task_state["status"] == TaskStatus.PASSED.value:
                continue

            state["current_task"] = task.id
            task_state["status"] = TaskStatus.RUNNING.value
            task_state["attempts"] += 1
            task_state["started_at"] = now_iso()
            task_state["finished_at"] = None
            task_state["last_error"] = None
            self.store.save(state)

            self._print(f"[{task.model}] {task.id}: {task.title}")
            result = self.executor.run(task.command, self.root)
            if result.stdout.strip():
                self._print(result.stdout.rstrip())
            if result.returncode != 0:
                return self._fail(task.id, result.stderr or f"exit code {result.returncode}")

            for check in task.checks:
                check_result = self.executor.run(check, self.root)
                if check_result.stdout.strip():
                    self._print(check_result.stdout.rstrip())
                if check_result.returncode != 0:
                    return self._fail(
                        task.id,
                        check_result.stderr or f"check exit code {check_result.returncode}",
                    )

            state = self.store.load()
            task_state = state["tasks"][task.id]
            task_state["status"] = TaskStatus.PASSED.value
            task_state["finished_at"] = now_iso()
            task_state["last_error"] = None
            state["current_task"] = None
            self.store.save(state)
            self._print(f"PASS {task.id}")

        state = self.store.load()
        state["status"] = WorkflowStatus.PASSED.value
        state["current_task"] = None
        self.store.save(state)
        self._print("workflow PASSED")
        return state

    def _fail(self, task_id: str, message: str) -> dict:
        state = self.store.load()
        task_state = state["tasks"][task_id]
        task_state["status"] = TaskStatus.FAILED.value
        task_state["finished_at"] = now_iso()
        task_state["last_error"] = message.strip()
        state["status"] = WorkflowStatus.FAILED.value
        state["current_task"] = task_id
        self.store.save(state)
        self._print(f"FAIL {task_id}: {task_state['last_error']}")
        return state
