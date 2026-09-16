from __future__ import annotations

from pathlib import Path

from .config import (
    HANDOFF_FILE,
    autodev_dir,
    load_models,
    load_repository_context,
    load_rolling_context,
)
from .models import Plan, TaskStatus
from .rolling_context import ContextPackBuilder
from .router import RuleRouter


class HandoffWriter:
    def __init__(self, root: Path):
        self.root = root
        self.path = autodev_dir(root) / HANDOFF_FILE

    @staticmethod
    def _route_text(item: dict) -> str:
        route = item.get("route") or {}
        if not route:
            return "-"
        return (
            f"{route.get('level')} / {route.get('provider')}:{route.get('model')} "
            f"via {route.get('executor')}"
        )

    def write(self, plan: Plan, state: dict) -> Path:
        passed_tasks = [
            task
            for task in plan.tasks
            if state["tasks"][task.id]["status"] == TaskStatus.PASSED.value
        ]
        pending_tasks = [
            task
            for task in plan.tasks
            if state["tasks"][task.id]["status"] != TaskStatus.PASSED.value
        ]
        next_task = pending_tasks[0] if pending_tasks else None

        lines = [
            "# AutoDev Handoff",
            "",
            f"- Project: `{plan.project}`",
            f"- Workflow: `{state['status']}`",
            f"- Current task: `{state.get('current_task') or 'none'}`",
            f"- Completed: {len(passed_tasks)}/{len(plan.tasks)}",
            f"- Next unresolved: `{next_task.id if next_task else 'none'}`",
            "- Conversation policy: keep the same canonical project conversation when possible.",
        ]

        repo = load_repository_context(self.root)
        rolling = load_rolling_context(self.root, project=plan.project)

        if next_task is not None:
            route = RuleRouter(load_models(self.root), repository_context=repo).route(next_task)
            requested_route = {
                "level": route.level.value,
                "provider": route.profile.provider,
                "model": route.profile.model,
                "executor": route.profile.executor,
                "reason": route.reason,
                "confidence": route.confidence,
            }
            pack = ContextPackBuilder().build(
                plan,
                state,
                next_task,
                rolling,
                repository=repo,
                requested_route=requested_route,
            )
            pack_text = pack.to_markdown().strip().splitlines()
            lines.extend(["", "## Next Task Context Pack", ""])
            if pack_text and pack_text[0].startswith("# "):
                pack_text = pack_text[1:]
                if pack_text and not pack_text[0].strip():
                    pack_text = pack_text[1:]
            lines.extend(pack_text)
        else:
            if passed_tasks:
                last_task = passed_tasks[-1]
                last_item = state["tasks"][last_task.id]
                lines.extend(
                    [
                        "",
                        "## Final completed task",
                        "",
                        f"- Stage / Step: `{last_task.stage_id}` / `{last_task.step_id}`",
                        f"- Task: `{last_task.id}` — {last_task.title}",
                        f"- Route: `{self._route_text(last_item)}`",
                    ]
                )
            if repo is not None:
                compact = repo.compact(max_files=8, max_facts=4)
                lines.extend(
                    [
                        "",
                        "## Final repository anchor",
                        "",
                        f"- Repository: `{compact['repository']}`",
                        f"- Branch: `{compact['branch'] or 'unknown'}`",
                        f"- Commit: `{compact['commit'] or 'unanchored'}`",
                        f"- CI: `{compact['ci_status']}`",
                    ]
                )

        lines.extend(
            [
                "",
                "## Unresolved task ledger",
                "",
                "| Stage | Step | Role | Task | Status | Attempts | Route | Last failure |",
                "| --- | --- | --- | --- | --- | ---: | --- | --- |",
            ]
        )
        visible = pending_tasks[:10]
        for task in visible:
            item = state["tasks"][task.id]
            route_text = self._route_text(item)
            failure_type = item.get("last_failure_type") or "-"
            failure_message = (item.get("last_error") or "-").replace("|", "\\|").replace("\n", " ")
            if len(failure_message) > 120:
                failure_message = failure_message[:117] + "..."
            failure_text = failure_type if failure_message == "-" else f"{failure_type}: {failure_message}"
            lines.append(
                f"| {task.stage_id} | {task.step_id} | {task.role.value} | {task.id} | "
                f"{item['status']} | {item.get('attempts', 0)} | {route_text} | {failure_text} |"
            )
        if len(pending_tasks) > len(visible):
            lines.append(
                f"\n_{len(pending_tasks) - len(visible)} additional unresolved task(s) omitted; "
                "use `autodev plan` for the full plan._"
            )
        if not pending_tasks:
            lines.append("| - | - | - | - | all passed | - | - | - |")

        lines.extend(
            [
                "",
                "## Resume rule",
                "",
                "Continue the same canonical conversation when possible; do not create a new chat merely to change reasoning effort.",
                "Use the Next Task Context Pack plus the relevant files; do not replay old chat history.",
                "Treat the repository commit above as the evidence anchor. If the branch moved, refresh commit-sensitive facts before making scope-sensitive decisions.",
                "If the workflow is FAILED/BLOCKED, inspect the last failure before using `autodev retry <task>`.",
                "",
            ]
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines), encoding="utf-8")
        return self.path
