from __future__ import annotations

from dev_task_router.config import load_models, write_default_files
from dev_task_router.deterministic_runner import DeterministicTaskRunner
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.models import Plan
from dev_task_router.router import RuleRouter
from dev_task_router.state import StateStore


def _plan(command: list[str]) -> Plan:
    return Plan.from_dict(
        {
            "version": 3,
            "project": "demo",
            "tasks": [
                {
                    "id": "unit",
                    "title": "Run deterministic verification",
                    "kind": "test",
                    "command": command,
                    "max_attempts": 3,
                }
            ],
        }
    )


def _runner(tmp_path, plan: Plan):
    write_default_files(tmp_path, plan.project)
    store = StateStore(tmp_path)
    store.create(plan)
    router = RuleRouter(load_models(tmp_path))
    evidence = ExecutionEvidenceLedger(tmp_path)
    runner = DeterministicTaskRunner(
        tmp_path,
        plan,
        store,
        router,
        evidence=evidence,
    )
    return store, evidence, runner


def test_deterministic_success_records_compact_evidence(tmp_path) -> None:
    plan = _plan(["python", "-c", "print('ok')"])
    _, evidence, runner = _runner(tmp_path, plan)

    result = runner.run(plan.tasks[0])
    events = evidence.events()

    assert result.status == "PASSED"
    assert [event.kind for event in events] == [
        "DETERMINISTIC_STARTED",
        "DETERMINISTIC_COMMAND_COMPLETED",
        "DETERMINISTIC_CHECKED",
        "STATE_RECORDED",
    ]
    assert events[0].data["level"] == "NONE"
    assert events[1].data["returncode"] == 0
    assert events[2].data["ok"] is True
    assert events[3].data["task_status"] == "PASSED"
    assert evidence.verify_chain() is True
    text = evidence.path.read_text(encoding="utf-8")
    assert "print('ok')" not in text


def test_deterministic_failure_records_debug_boundary_without_model_promotion(tmp_path) -> None:
    plan = _plan(["python", "-c", "raise SystemExit(7)"])
    store, evidence, runner = _runner(tmp_path, plan)

    first = runner.run(plan.tasks[0])
    second = runner.run(plan.tasks[0])
    events = evidence.events()
    state = store.load()

    assert first.status == "DEBUG_TASK_REQUIRED"
    assert second.status == "DEBUG_TASK_REQUIRED"
    assert [event.kind for event in events] == [
        "DETERMINISTIC_STARTED",
        "DETERMINISTIC_COMMAND_COMPLETED",
        "STATE_RECORDED",
    ]
    assert events[1].data["returncode"] == 7
    assert events[2].data["last_failure_type"] == "DETERMINISTIC_COMMAND"
    assert state["tasks"]["unit"]["route"]["level"] == "NONE"
    assert state["tasks"]["unit"]["attempts"] == 1
    assert evidence.verify_chain() is True
