from __future__ import annotations

from pathlib import Path

from .config import HANDOFF_FILE, autodev_dir
from .models import Plan, TaskStatus


class HandoffWriter:
    def __init__(self, root: Path):
        self.path = autodev_dir(root) / HANDOFF_FILE

    def write(self, plan: Plan, state: dict) -> Path:
        passed = [
            task.id
            for task in plan.tasks
            if state["tasks"][task.id]["status"] == TaskStatus.PASSED.value
        ]
        pending = [
            task.id
            for task in plan.tasks
            if state["tasks"][task.id]["status"] != TaskStatus.PASSED.value
        ]
        lines = [
            "# AutoDev Handoff",
            "",
            f"- Project: `{plan.project}`",
            f"- Workflow: `{state['status']}`",
            f"- Current task: `{state.get('current_task') or 'none'}`",
            f"- Completed: {len(passed)}/{len(plan.tasks)}",
            f"- Next unresolved: `{pending[0] if pending else 'none'}`",
            "",
            "## Tasks",
            "",
            "| Stage | Step | Role | Task | Status | Route |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for task in plan.tasks:
            item = state["tasks"][task.id]
            route = item.get("route") or {}
            route_text = "-"
            if route:
                route_text = (
                    f"{route.get('level')} / {route.get('provider')}:{route.get('model')} "
                    f"via {route.get('executor')}"
                )
            lines.append(
                f"| {task.stage_id} | {task.step_id} | {task.role.value} | {task.id} | "
                f"{item['status']} | {route_text} |"
            )
        lines.extend(
            [
                "",
                "## Resume rule",
                "",
                "Read this file plus the relevant task files; do not replay old chat history.",
                "",
            ]
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines), encoding="utf-8")
        return self.path
