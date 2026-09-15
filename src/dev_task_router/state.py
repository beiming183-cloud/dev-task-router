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

    def create(self, plan: Plan) -> dict[str, Any]:
        state = {
            "version": 1,
            "project": plan.project,
            "status": WorkflowStatus.READY.value,
            "current_task": None,
            "updated_at": now_iso(),
            "tasks": {
                task.id: {
                    "status": TaskStatus.PENDING.value,
                    "attempts": 0,
                    "last_error": None,
                    "started_at": None,
                    "finished_at": None,
                }
                for task in plan.tasks
            },
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
        if expected != actual:
            raise ValueError("plan tasks changed after state creation; remove .autodev/state.json to reinitialize")

        return state
