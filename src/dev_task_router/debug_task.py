from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import PLAN_FILE, autodev_dir
from .execution_evidence import ExecutionEvidenceLedger
from .handoff import HandoffWriter
from .models import Plan, TaskSpec, WorkflowStatus
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


@dataclass(frozen=True, slots=True)
class DebugTaskActivation:
    source_task_id: str
    debug_task_id: str
    candidate_path: str
    inserted: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_task_id": self.source_task_id,
            "debug_task_id": self.debug_task_id,
            "candidate_path": self.candidate_path,
            "inserted": self.inserted,
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


class DebugTaskActivator:
    """Explicitly insert a materialized debug Task before its failed NONE source.

    Activation is intentionally separate from materialization. The source Task remains
    failed until the debug Task itself reaches verified PASS. Inserting the debug Task
    before the source means the normal project loop executes the debug Task first and
    can later return to the original deterministic command without promoting NONE.
    """

    def __init__(
        self,
        root: Path,
        plan: Plan,
        store: StateStore,
        *,
        evidence: ExecutionEvidenceLedger | None = None,
    ):
        self.root = root.resolve()
        self.plan = plan
        self.store = store
        self.evidence = evidence or ExecutionEvidenceLedger(self.root)

    def _source_id(self, requested: str | None) -> str:
        state = self.store.ensure_for_plan(self.plan)
        if requested:
            source_id = requested.strip()
            if source_id not in state["tasks"]:
                raise ValueError(f"unknown task: {source_id}")
            if not state["tasks"][source_id].get("debug_task_required"):
                raise ValueError(f"task {source_id} does not require a debug Task")
            return source_id
        for task in self.plan.tasks:
            if state["tasks"][task.id].get("debug_task_required"):
                return task.id
        raise ValueError("no deterministic failure is waiting for debug Task activation")

    @staticmethod
    def _task_containers(data: dict[str, Any]):
        stages = data.get("stages")
        if stages is not None:
            if not isinstance(stages, list):
                raise ValueError("plan.stages must be a list")
            for stage in stages:
                if not isinstance(stage, dict):
                    continue
                stage_id = str(stage.get("id", "default"))
                steps = stage.get("steps", [])
                if not isinstance(steps, list):
                    continue
                for step in steps:
                    if not isinstance(step, dict):
                        continue
                    tasks = step.get("tasks")
                    if isinstance(tasks, list):
                        yield stage_id, str(step.get("id", "default")), tasks
            return
        tasks = data.get("tasks")
        if isinstance(tasks, list):
            yield "default", "default", tasks

    def _candidate(self, source_id: str, state: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
        source = state["tasks"][source_id]
        relative = str(source.get("debug_task_file") or "").strip()
        if not relative:
            raise ValueError(
                f"task {source_id} has no materialized debug Task file; rerun materialization first"
            )
        path = (self.root / relative).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("debug Task candidate path escapes the project root") from exc
        if not path.is_file():
            raise FileNotFoundError(path)
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("debug Task candidate must be a YAML mapping")
        expected_id = str(source.get("debug_task_id") or f"{source_id}-debug")
        if str(raw.get("id", "")).strip() != expected_id:
            raise ValueError("debug Task candidate id does not match the materialized state")
        metadata = raw.get("metadata")
        if not isinstance(metadata, dict) or str(metadata.get("generated_from", "")) != source_id:
            raise ValueError("debug Task candidate provenance does not match its source Task")
        if raw.get("level") is not None or raw.get("model") is not None:
            raise ValueError("debug Task candidate must not pin a model level; classify it independently")
        return path, raw

    def activate(self, task_id: str | None = None) -> DebugTaskActivation:
        source_id = self._source_id(task_id)
        state = self.store.load()
        candidate_path, candidate = self._candidate(source_id, state)
        debug_id = str(candidate["id"])
        plan_path = autodev_dir(self.root) / PLAN_FILE
        plan_data = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        if not isinstance(plan_data, dict):
            raise ValueError("plan.yaml must contain a mapping")

        source_location: tuple[str, str, list[Any], int] | None = None
        debug_location: tuple[str, str, int] | None = None
        for stage_id, step_id, tasks in self._task_containers(plan_data):
            for index, raw_task in enumerate(tasks):
                if not isinstance(raw_task, dict):
                    continue
                raw_id = str(raw_task.get("id", "")).strip()
                if raw_id == source_id:
                    source_location = (stage_id, step_id, tasks, index)
                if raw_id == debug_id:
                    debug_location = (stage_id, step_id, index)

        if source_location is None:
            raise ValueError(f"source task {source_id} is missing from plan.yaml")
        stage_id, step_id, tasks, source_index = source_location
        TaskSpec.from_dict(candidate, stage_id=stage_id, step_id=step_id)

        inserted = False
        if debug_location is None:
            tasks.insert(source_index, candidate)
            # Validate the complete mutated plan before touching disk.
            new_plan = Plan.from_dict(plan_data)
            tmp = plan_path.with_suffix(".yaml.tmp")
            tmp.write_text(
                yaml.safe_dump(plan_data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            tmp.replace(plan_path)
            inserted = True
        else:
            debug_stage, debug_step, debug_index = debug_location
            if debug_stage != stage_id or debug_step != step_id or debug_index >= source_index:
                raise ValueError(
                    "existing debug Task is not positioned before its source Task in the same step"
                )
            new_plan = Plan.from_dict(plan_data)

        state = self.store.ensure_for_plan(new_plan)
        source_state = state["tasks"][source_id]
        debug_state = state["tasks"][debug_id]
        source_state["debug_task_activated"] = True
        source_state["debug_task_activated_at"] = now_iso()
        debug_state["generated_from_debug_source"] = source_id
        debug_state["debug_candidate_file"] = candidate_path.relative_to(self.root).as_posix()
        state["status"] = WorkflowStatus.READY.value
        state["current_task"] = None
        self.store.save(state)

        self.evidence.record(
            task_id=source_id,
            kind="DEBUG_TASK_ACTIVATED",
            data={
                "debug_task_id": debug_id,
                "candidate_path": candidate_path.relative_to(self.root).as_posix(),
                "inserted": inserted,
                "auto_execute": False,
            },
        )
        HandoffWriter(self.root).write(new_plan, state)
        return DebugTaskActivation(
            source_task_id=source_id,
            debug_task_id=debug_id,
            candidate_path=candidate_path.relative_to(self.root).as_posix(),
            inserted=inserted,
        )
