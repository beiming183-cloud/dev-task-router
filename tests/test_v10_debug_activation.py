from __future__ import annotations

import sys

import pytest
import yaml

from dev_task_router.config import load_models, load_plan, write_default_files
from dev_task_router.debug_task import DebugTaskActivator, DebugTaskMaterializer
from dev_task_router.deterministic_runner import DeterministicTaskRunner
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.local_project_loop import LocalProjectLoop
from dev_task_router.local_session import LocalCycleResult
from dev_task_router.models import ModelLevel, Plan, TaskSpec, TaskStatus
from dev_task_router.router import RuleRouter
from dev_task_router.state import StateStore


def _write_plan(root) -> Plan:
    data = {
        "version": 3,
        "project": "demo",
        "stages": [
            {
                "id": "verify",
                "title": "Verify",
                "steps": [
                    {
                        "id": "smoke",
                        "title": "Smoke",
                        "tasks": [
                            {
                                "id": "check",
                                "title": "Deterministic check",
                                "kind": "test",
                                "level": "NONE",
                                "command": [sys.executable, "-c", "print('fixed')"],
                                "checks": [],
                                "max_attempts": 1,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    path = root / ".autodev" / "plan.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_plan(root)


def _seed_failed_source(root, plan: Plan) -> StateStore:
    store = StateStore(root)
    state = store.create(plan)
    item = state["tasks"]["check"]
    item["status"] = TaskStatus.FAILED.value
    item["attempts"] = 1
    item["last_error"] = "exit code 1"
    item["last_failure_type"] = "DETERMINISTIC_COMMAND"
    item["failures"] = [
        {
            "attempt": 1,
            "type": "DETERMINISTIC_COMMAND",
            "message": "exit code 1",
            "route": {"level": "NONE"},
        }
    ]
    item["debug_task_required"] = True
    store.save(state)
    return store


def test_state_store_allows_additive_tasks_but_refuses_history_deletion(tmp_path) -> None:
    first = Plan(project="demo", tasks=[TaskSpec(id="a", title="A", prompt="do A")])
    store = StateStore(tmp_path)
    state = store.create(first)
    state["tasks"]["a"]["attempts"] = 2
    state["tasks"]["a"]["failures"] = [{"attempt": 1, "type": "CHECK"}]
    store.save(state)

    extended = Plan(
        project="demo",
        tasks=[
            TaskSpec(id="debug", title="Debug", prompt="debug A"),
            TaskSpec(id="a", title="A", prompt="do A"),
        ],
    )
    migrated = store.ensure_for_plan(extended)
    assert migrated["tasks"]["a"]["attempts"] == 2
    assert migrated["tasks"]["a"]["failures"] == [{"attempt": 1, "type": "CHECK"}]
    assert migrated["tasks"]["debug"]["status"] == TaskStatus.PENDING.value

    shrunk = Plan(project="demo", tasks=[TaskSpec(id="debug", title="Debug", prompt="debug A")])
    with pytest.raises(ValueError, match="refusing to discard durable task state"):
        store.ensure_for_plan(shrunk)


def test_debug_activation_is_independent_and_precedes_failed_none_source(tmp_path) -> None:
    write_default_files(tmp_path, "demo")
    plan = _write_plan(tmp_path)
    store = _seed_failed_source(tmp_path, plan)
    candidate = DebugTaskMaterializer(tmp_path, plan, store).materialize("check")

    activation = DebugTaskActivator(tmp_path, plan, store).activate("check")
    assert activation.inserted is True
    assert activation.debug_task_id == candidate.debug_task_id == "check-debug"

    activated_plan = load_plan(tmp_path)
    assert [task.id for task in activated_plan.tasks] == ["check-debug", "check"]
    debug = activated_plan.tasks[0]
    source = activated_plan.tasks[1]
    assert debug.level is None
    assert source.level == ModelLevel.NONE
    assert RuleRouter(load_models(tmp_path)).route(debug).level != ModelLevel.NONE

    state = store.ensure_for_plan(activated_plan)
    assert state["tasks"]["check"]["status"] == TaskStatus.FAILED.value
    assert state["tasks"]["check-debug"]["status"] == TaskStatus.PENDING.value
    assert state["tasks"]["check-debug"]["generated_from_debug_source"] == "check"

    # A fresh invocation is idempotent and does not duplicate the generated Task.
    second = DebugTaskActivator(tmp_path, activated_plan, store).activate("check")
    assert second.inserted is False
    assert [task.id for task in load_plan(tmp_path).tasks] == ["check-debug", "check"]


def test_debug_pass_reopens_original_none_task_without_erasing_failure_history(tmp_path) -> None:
    write_default_files(tmp_path, "demo")
    plan = _write_plan(tmp_path)
    store = _seed_failed_source(tmp_path, plan)
    DebugTaskMaterializer(tmp_path, plan, store).materialize("check")
    DebugTaskActivator(tmp_path, plan, store).activate("check")
    activated_plan = load_plan(tmp_path)

    state = store.ensure_for_plan(activated_plan)
    state["tasks"]["check-debug"]["status"] = TaskStatus.PASSED.value
    original_failures = list(state["tasks"]["check"]["failures"])
    store.save(state)

    class EmptyCycle:
        pass

    loop = LocalProjectLoop(tmp_path, activated_plan, store, EmptyCycle())
    loop._reopen_debug_source_after_pass(
        LocalCycleResult(
            task_id="check-debug",
            status="PASSED",
            dispatch_id="debug-dispatch",
            infrastructure_failure=False,
            message="debug fix verified",
        )
    )

    reopened = store.load()["tasks"]["check"]
    assert reopened["status"] == TaskStatus.PENDING.value
    assert reopened["attempts"] == 1
    assert reopened["failures"] == original_failures
    assert reopened["debug_task_required"] is False
    assert reopened["debug_task_recheck_pending"] is True
    assert reopened["debug_task_resolved_by"] == "check-debug"

    source = next(task for task in activated_plan.tasks if task.id == "check")
    router = RuleRouter(load_models(tmp_path))
    result = DeterministicTaskRunner(
        tmp_path,
        activated_plan,
        store,
        router,
        evidence=ExecutionEvidenceLedger(tmp_path),
    ).run(source)
    assert result.status == "PASSED"
    final = store.load()["tasks"]["check"]
    assert final["status"] == TaskStatus.PASSED.value
    assert final["attempts"] == 2
    assert final["failures"] == original_failures
    kinds = [event.kind for event in ExecutionEvidenceLedger(tmp_path).events()]
    assert "DEBUG_TASK_ACTIVATED" in kinds
    assert "DEBUG_SOURCE_REOPENED" in kinds
    assert "DETERMINISTIC_STARTED" in kinds
    assert "DETERMINISTIC_CHECKED" in kinds
