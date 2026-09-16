from __future__ import annotations

from pathlib import Path

from .config import HANDOFF_FILE, autodev_dir, load_repository_context
from .models import Plan, TaskStatus


class HandoffWriter:
    def __init__(self, root: Path):
        self.root = root
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
        ]

        repo = load_repository_context(self.root)
        if repo is not None:
            compact = repo.compact(max_files=12, max_facts=6)
            lines.extend(
                [
                    "",
                    "## Repository evidence",
                    "",
                    f"- Source: `{compact['source']}`",
                    f"- Repository: `{compact['repository']}`",
                    f"- Branch: `{compact['branch'] or 'unknown'}`",
                    f"- Commit: `{compact['commit'] or 'unanchored'}`",
                    f"- PR: `{compact['pr_number'] or 'none'}`",
                    f"- CI: `{compact['ci_status']}`",
                ]
            )
            if compact["ci_checks"]:
                lines.append(f"- CI checks: {', '.join(compact['ci_checks'])}")
            if compact["files"]:
                lines.append("- Relevant files:")
                lines.extend(f"  - `{path}`" for path in compact["files"])
                if compact["file_count_total"] > len(compact["files"]):
                    lines.append(
                        f"  - ... {compact['file_count_total'] - len(compact['files'])} more omitted"
                    )
            if compact["evidence_tags"]:
                lines.append(f"- Evidence tags: {', '.join(compact['evidence_tags'])}")
            if compact["facts"]:
                lines.append("- Verified facts:")
                lines.extend(f"  - {fact}" for fact in compact["facts"])

        lines.extend(
            [
                "",
                "## Tasks",
                "",
                "| Stage | Step | Role | Task | Status | Attempts | Route | Last failure |",
                "| --- | --- | --- | --- | --- | ---: | --- | --- |",
            ]
        )
        for task in plan.tasks:
            item = state["tasks"][task.id]
            route = item.get("route") or {}
            route_text = "-"
            if route:
                route_text = (
                    f"{route.get('level')} / {route.get('provider')}:{route.get('model')} "
                    f"via {route.get('executor')}"
                )
            failure_type = item.get("last_failure_type") or "-"
            failure_message = (item.get("last_error") or "-").replace("|", "\\|").replace("\n", " ")
            if len(failure_message) > 120:
                failure_message = failure_message[:117] + "..."
            failure_text = failure_type if failure_message == "-" else f"{failure_type}: {failure_message}"
            lines.append(
                f"| {task.stage_id} | {task.step_id} | {task.role.value} | {task.id} | "
                f"{item['status']} | {item.get('attempts', 0)} | {route_text} | {failure_text} |"
            )
        lines.extend(
            [
                "",
                "## Resume rule",
                "",
                "Read this file plus the relevant task files; do not replay old chat history.",
                "Treat the repository commit above as the evidence anchor. If the branch moved, refresh GitHub evidence before making scope-sensitive decisions.",
                "If the workflow is FAILED/BLOCKED, inspect the last failure before using `autodev retry <task>`.",
                "",
            ]
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(lines), encoding="utf-8")
        return self.path
