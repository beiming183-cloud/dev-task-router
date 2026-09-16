from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import autodev_dir
from .models import Plan, TaskSpec
from .state import StateStore, now_iso


@dataclass(frozen=True, slots=True)
class DebugTaskCandidate:
    source_task_id: str
    debug_task_id: str
    path: Path
    task: dict

    def to_dict(self) -> dict:
        return {
            "source_task_id": self.source_task_id,
            "debug_task_id": self.debug_task_id,
            "path": self.path.as_posix(),
            "task": self.task,
        }


class DebugTaskMaterializer:
    """Create a separate debug Task candidate from deterministic failure evidence.

    The failed NONE Task itself is never promoted. The generated candidate has no
    explicit level; it must go through the ordinary classifier independently.
    """

    def __init__(self, root: Path, plan: Plan, store: StateStore):
        self.root = root
        self.plan = plan
        self.store = store

    def _task(self, task_id: str) -> TaskSpec:
        for task in self.plan.tasks:
            if task.id == task_id:
                return task
        raise ValueError(f"unknown task: {task_id}")

    def materialize(self, task_id: str) -> DebugTaskCandidate:
        task = self._task(task_id)
        state = self.store.ensure_for_plan(self.plan)
        item = state["tasks"][task_id]
        if not item.get("debug_task_required"):
            raise ValueError(f"task {task_id} does not require a debug Task")

        failure_type = str(item.get("last_failure_type") or "DETERMINISTIC_FAILURE")
        message = str(item.get("last_error") or "deterministic command/check failed").strip()
        if len(message) > 2000:
            message = message[:2000] + "…"
        debug_id = f"{task.id}-debug"
        command = task.command or []
        command_text = json.dumps(command, ensure_ascii=False)
        prompt = (
            f"Investigate the root cause of deterministic Task {task.id!r} failure. "
            "Treat the failed deterministic step as evidence only; do not promote the original NONE Task.\n\n"
            f"Original title: {task.title}\n"
            f"Failure type: {failure_type}\n"
            f"Failure evidence: {message}\n"
            f"Original command: {command_text}\n\n"
            "Identify the root cause from repository/runtime evidence, make the smallest justified fix when appropriate, "
            "and rerun the original deterministic command/check before claiming success."
        )
        candidate_task = {
            "id": debug_id,
            "title": f"Debug failure from {task.id}: {task.title}",
            "kind": "normal_debug",
            "prompt": prompt,
            "acceptance": [
                "Root cause is identified with concrete evidence",
                "Any fix is scoped to the diagnosed cause",
                "The original deterministic command/check is rerun after the fix",
            ],
            "max_attempts": max(2, int(task.max_attempts)),
            "escalate_after": 1,
            "review": task.review,
            "metadata": {
                "generated_from": task.id,
                "failure_type": failure_type,
                "generated_at": now_iso(),
            },
        }

        path = autodev_dir(self.root) / "debug-tasks" / f"{debug_id}.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(candidate_task, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

        state = self.store.load()
        state_item = state["tasks"][task_id]
        state_item["debug_task_file"] = path.relative_to(self.root).as_posix()
        state_item["debug_task_id"] = debug_id
        self.store.save(state)

        return DebugTaskCandidate(
            source_task_id=task.id,
            debug_task_id=debug_id,
            path=path,
            task=candidate_task,
        )
