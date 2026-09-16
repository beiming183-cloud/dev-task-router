from __future__ import annotations

from dev_task_router.config import load_models, write_default_files
from dev_task_router.deterministic_runner import DeterministicTaskRunner
from dev_task_router.models import Plan
from dev_task_router.router import RuleRouter
from dev_task_router.state import StateStore


def _plan(command: list[str]) -> Plan:
    return Plan.from_dict(
        {
            "version": 3,
            "project": "demo",
            "stages": [
                {
                    "id": "verify",
                    "steps": [
                        {
                            "id": "tests",
                            "tasks": [
                                {
                                    "id": "unit",
                                    "title": "Run unit tests",
                                    "kind": "test",
                                    "command": command,
                                    "max_attempts": 3,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def _runner(tmp_path, plan: Plan):
    write_default_files(tmp_path, plan.project)
    store = StateStore(tmp_path)
    store.create(plan)
    router = RuleRouter(load_models(tmp_path))
    return store, DeterministicTaskRunner(tmp_path, plan, store, router)


def test_deterministic_success_passes_without_model_dispatch(tmp_path) -> None:
    plan = _plan(["python", "-c", "print('ok')"])
    store, runner = _runner(tmp_path, plan)

    result = runner.run(plan.tasks[0])
    state = store.load()

    assert result.status == "PASSED"
    assert state["tasks"]["unit"]["status"] == "PASSED"
    assert state["tasks"]["unit"]["attempts"] == 1
    assert state["tasks"]["unit"]["route"]["level"] == "NONE"
    assert state["status"] == "PASSED"
    assert not (tmp_path / ".autodev" / "local-dispatch.json").exists()


def test_deterministic_failure_requires_separate_debug_task_and_is_not_retried(tmp_path) -> None:
    script = (
        "from pathlib import Path; "
        "p=Path('counter.txt'); "
        "p.write_text(str(int(p.read_text())+1) if p.exists() else '1'); "
        "raise SystemExit(3)"
    )
    plan = _plan(["python", "-c", script])
    store, runner = _runner(tmp_path, plan)

    first = runner.run(plan.tasks[0])
    second = runner.run(plan.tasks[0])
    state = store.load()

    assert first.status == "DEBUG_TASK_REQUIRED"
    assert second.status == "DEBUG_TASK_REQUIRED"
    assert "classify it independently" in first.message
    assert state["tasks"]["unit"]["status"] == "FAILED"
    assert state["tasks"]["unit"]["last_failure_type"] == "DETERMINISTIC_COMMAND"
    assert state["tasks"]["unit"]["debug_task_required"] is True
    assert state["tasks"]["unit"]["attempts"] == 1
    assert (tmp_path / "counter.txt").read_text(encoding="utf-8") == "1"
