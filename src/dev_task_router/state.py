from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import STATE_FILE, autodev_dir
from .models import Plan, TaskStatus, WorkflowStatus


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class StateStore:
    def __init__(self, root: Path):
        self.path = autodev_dir(root) / STATE_FILE

    def exists(self) -> bool:
        return self.path.exists()

    @staticmethod
    def _task_state(task) -> dict[str, Any]:
        return {
            "status": TaskStatus.PENDING.value,
            "attempts": 0,
            "retry_cycles": 0,
            "last_error": None,
            "last_failure_type": None,
            "started_at": None,
            "finished_at": None,
            "stage": task.stage_id,
            "step": task.step_id,
            "role": task.role.value,
            "kind": task.kind,
            "route": None,
            "route_history": [],
            "failures": [],
            "review": None,
        }

    def create(self, plan: Plan) -> dict[str, Any]:
        state = {
            "version": 3,
            "project": plan.project,
            "status": WorkflowStatus.READY.value,
            "current_task": None,
            "updated_at": now_iso(),
            "tasks": {task.id: self._task_state(task) for task in plan.tasks},
        }
        self.save(state)
        return state

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        return json.loads(self.path.read_text(encoding="utf-8"))

    def save(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        state["updated_at"] = now_iso()
        self.path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def ensure_for_plan(self, plan: Plan) -> dict[str, Any]:
        if not self.exists():
            return self.create(plan)

        state = self.load()
        if state.get("project") != plan.project:
            raise ValueError("state project does not match plan project")

        expected = {task.id for task in plan.tasks}
        actual = set(state.get("tasks", {}))
        removed = actual - expected
        if removed:
            raise ValueError(
                "plan removed tasks after state creation; refusing to discard durable task state: "
                + ", ".join(sorted(removed))
            )

        # V1.0 permits additive Task materialization (for example an independently
        # classified debug Task). Existing durable Task history is never replaced.
        for task in plan.tasks:
            if task.id not in state["tasks"]:
                state["tasks"][task.id] = self._task_state(task)

        # V0.1/V0.2 state files remain readable; enrich them in place.
        state["version"] = 3
        for task in plan.tasks:
            task_state = state["tasks"][task.id]
            task_state["stage"] = task.stage_id
            task_state["step"] = task.step_id
            task_state["role"] = task.role.value
            task_state["kind"] = task.kind
            task_state.setdefault("route", None)
            task_state.setdefault("route_history", [])
            task_state.setdefault("failures", [])
            task_state.setdefault("review", None)
            task_state.setdefault("last_failure_type", None)
            task_state.setdefault("retry_cycles", 0)
        self.save(state)
        return state

    def reset_task(self, plan: Plan, task_id: str) -> dict[str, Any]:
        state = self.ensure_for_plan(plan)
        if task_id not in state["tasks"]:
            raise ValueError(f"unknown task: {task_id}")
        item = state["tasks"][task_id]
        item["status"] = TaskStatus.PENDING.value
        item["attempts"] = 0
        item["retry_cycles"] = int(item.get("retry_cycles", 0)) + 1
        item["last_error"] = None
        item["last_failure_type"] = None
        item["started_at"] = None
        item["finished_at"] = None
        item["review"] = None
        state["status"] = WorkflowStatus.READY.value
        state["current_task"] = None
        self.save(state)
        return state
