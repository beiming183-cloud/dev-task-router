from __future__ import annotations

from dataclasses import dataclass

from dev_task_router.config import (
    load_rolling_context,
    save_rolling_context,
    write_default_files,
)
from dev_task_router.local_project_loop import LocalProjectLoop
from dev_task_router.local_session import LocalCycleResult
from dev_task_router.models import Plan
from dev_task_router.response_monitor import ResponseCollectionResult
from dev_task_router.rolling_context import RollingProjectContext
from dev_task_router.state import StateStore


def _plan() -> Plan:
    return Plan.from_dict(
        {
            "version": 3,
            "project": "demo",
            "stages": [
                {
                    "id": "stage",
                    "steps": [
                        {
                            "id": "step",
                            "tasks": [
                                {
                                    "id": "one",
                                    "title": "First feature",
                                    "kind": "normal_code",
                                    "prompt": "Implement first feature.",
                                },
                                {
                                    "id": "two",
                                    "title": "Second feature",
                                    "kind": "normal_code",
                                    "prompt": "Implement second feature.",
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )


@dataclass
class FakeCycle:
    results: list[LocalCycleResult]
    index: int = 0

    def run_next(self) -> LocalCycleResult:
        if self.index >= len(self.results):
            return LocalCycleResult("", "NO_TASK", None, False, "done")
        result = self.results[self.index]
        self.index += 1
        return result


def _root(tmp_path):
    plan = _plan()
    write_default_files(tmp_path, plan.project)
    store = StateStore(tmp_path)
    store.create(plan)
    save_rolling_context(
        tmp_path,
        RollingProjectContext.from_dict(
            {
                "project": plan.project,
                "goal": "Finish the project safely.",
                "decisions": ["Keep one canonical conversation"],
                "constraints": ["Do not infer durable decisions from model prose"],
                "last_commit": "anchor-old",
            }
        ),
    )
    return plan, store


def test_verified_pass_updates_only_machine_verified_rolling_facts(tmp_path) -> None:
    plan, store = _root(tmp_path)
    response = ResponseCollectionResult(
        completed=True,
        response_text="MODEL PROSE THAT MUST NOT BECOME A DURABLE DECISION",
        polls=3,
        saw_activity=True,
        reason="stable",
    )
    cycle = FakeCycle(
        [
            LocalCycleResult(
                "one",
                "PASSED",
                "abcdef1234567890",
                False,
                "checker passed",
                response=response,
            )
        ]
    )
    loop = LocalProjectLoop(tmp_path, plan, store, cycle)  # type: ignore[arg-type]

    result = loop.run_one()
    rolling = load_rolling_context(tmp_path, project=plan.project)
    text = str(rolling.to_dict())

    assert result.status == "PASSED"
    assert rolling.task_notes["one"] == ("Verified PASS by Checker; dispatch=abcdef123456.",)
    assert rolling.stage_notes["stage"] == ("Verified PASS one: First feature.",)
    assert rolling.last_commit == "anchor-old"
    assert "MODEL PROSE" not in text
    assert rolling.decisions == ("Keep one canonical conversation",)


def test_rolling_note_updates_are_normalized_and_deduplicated() -> None:
    context = RollingProjectContext.empty("demo")
    context = context.with_task_note("one", "  Verified   PASS  ")
    context = context.with_task_note("one", "verified pass")
    context = context.with_stage_note("stage", "Task one passed")
    context = context.with_stage_note("stage", " task   one   passed ")

    assert context.task_notes["one"] == ("Verified PASS",)
    assert context.stage_notes["stage"] == ("Task one passed",)


def test_project_loop_continues_across_pass_and_real_check_failure(tmp_path) -> None:
    plan, store = _root(tmp_path)
    cycle = FakeCycle(
        [
            LocalCycleResult("one", "CHECK_FAILED", "d1", False, "check failed"),
            LocalCycleResult("one", "PASSED", "d2", False, "retry passed"),
            LocalCycleResult("two", "PASSED", "d3", False, "passed"),
            LocalCycleResult("", "NO_TASK", None, False, "done"),
        ]
    )
    loop = LocalProjectLoop(tmp_path, plan, store, cycle)  # type: ignore[arg-type]

    result = loop.run_until_blocked(max_cycles=10)
    rolling = load_rolling_context(tmp_path, project=plan.project)

    assert result.stop_reason == "COMPLETE"
    assert [item.status for item in result.cycles] == [
        "CHECK_FAILED",
        "PASSED",
        "PASSED",
        "NO_TASK",
    ]
    assert "one" in rolling.task_notes
    assert "two" in rolling.task_notes


def test_project_loop_stops_on_waiting_response_instead_of_resending(tmp_path) -> None:
    plan, store = _root(tmp_path)
    cycle = FakeCycle(
        [
            LocalCycleResult("one", "WAITING_RESPONSE", "d1", True, "timeout"),
            LocalCycleResult("one", "PASSED", "d1", False, "would be later"),
        ]
    )
    loop = LocalProjectLoop(tmp_path, plan, store, cycle)  # type: ignore[arg-type]

    result = loop.run_until_blocked(max_cycles=10)

    assert result.stop_reason == "WAITING_RESPONSE"
    assert len(result.cycles) == 1
    assert cycle.index == 1


def test_project_loop_honors_max_cycle_guard(tmp_path) -> None:
    plan, store = _root(tmp_path)
    cycle = FakeCycle(
        [
            LocalCycleResult("one", "CHECK_FAILED", f"d{i}", False, "failed")
            for i in range(10)
        ]
    )
    loop = LocalProjectLoop(tmp_path, plan, store, cycle)  # type: ignore[arg-type]

    result = loop.run_until_blocked(max_cycles=3)

    assert result.stop_reason == "MAX_CYCLES"
    assert len(result.cycles) == 3
    assert cycle.index == 3
