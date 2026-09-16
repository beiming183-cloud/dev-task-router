from __future__ import annotations

import yaml

from dev_task_router.classifier import DifficultyClassifier
from dev_task_router.debug_task import DebugTaskMaterializer
from dev_task_router.models import ModelLevel, Plan, TaskSpec
from dev_task_router.state import StateStore


def test_debug_task_candidate_is_separate_and_reclassified(tmp_path) -> None:
    source = TaskSpec(
        id="build-smoke",
        title="Run smoke build",
        kind="build",
        command=["python", "-m", "compileall", "src"],
    )
    plan = Plan(project="demo", tasks=[source])
    store = StateStore(tmp_path)
    state = store.ensure_for_plan(plan)
    item = state["tasks"][source.id]
    item["status"] = "FAILED"
    item["last_failure_type"] = "DETERMINISTIC_COMMAND"
    item["last_error"] = "compile failed in src/example.py"
    item["debug_task_required"] = True
    store.save(state)

    candidate = DebugTaskMaterializer(tmp_path, plan, store).materialize(source.id)
    raw = yaml.safe_load(candidate.path.read_text(encoding="utf-8"))

    assert candidate.debug_task_id == "build-smoke-debug"
    assert raw["kind"] == "normal_debug"
    assert "level" not in raw
    assert "DETERMINISTIC_COMMAND" in raw["prompt"]
    assert "compile failed" in raw["prompt"]

    parsed = TaskSpec.from_dict(raw)
    assessment = DifficultyClassifier().classify(parsed)
    assert assessment.level != ModelLevel.NONE

    saved = store.load()["tasks"][source.id]
    assert saved["debug_task_id"] == candidate.debug_task_id
    assert saved["debug_task_file"].endswith("build-smoke-debug.yaml")


def test_debug_task_requires_explicit_failure_evidence(tmp_path) -> None:
    task = TaskSpec(id="test", title="Run tests", kind="test", command=["pytest"])
    plan = Plan(project="demo", tasks=[task])
    store = StateStore(tmp_path)
    store.ensure_for_plan(plan)

    materializer = DebugTaskMaterializer(tmp_path, plan, store)
    try:
        materializer.materialize(task.id)
    except ValueError as exc:
        assert "does not require a debug Task" in str(exc)
    else:
        raise AssertionError("expected materialization to reject a non-failed task")
