from __future__ import annotations

from dataclasses import dataclass

from dev_task_router.config import write_default_files
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.local_loop import LocalConversationOrchestrator
from dev_task_router.local_session import LocalSessionStore, LocalTaskCycle
from dev_task_router.models import Plan
from dev_task_router.recovery import LocalRecoveryController
from dev_task_router.response_monitor import (
    ConversationResponseMonitor,
    ResponseBaseline,
    ResponseSnapshot,
)
from dev_task_router.state import StateStore


def _plan() -> Plan:
    return Plan.from_dict(
        {
            "version": 3,
            "project": "demo",
            "tasks": [
                {
                    "id": "task",
                    "title": "Implement feature",
                    "kind": "normal_code",
                    "prompt": "Implement feature.",
                    "max_attempts": 2,
                }
            ],
        }
    )


@dataclass
class StaticSource:
    value: ResponseSnapshot

    def snapshot(self) -> ResponseSnapshot:
        return self.value


def _cycle(tmp_path):
    plan = _plan()
    write_default_files(tmp_path, plan.project)
    store = StateStore(tmp_path)
    store.create(plan)
    orchestrator = LocalConversationOrchestrator(tmp_path, plan, store)
    monitor = ConversationResponseMonitor(
        StaticSource(ResponseSnapshot(False, ("old",))),
        poll_interval_seconds=1,
        timeout_seconds=1,
        stable_polls=1,
    )
    cycle = LocalTaskCycle(tmp_path, plan, store, orchestrator, monitor)
    envelope = orchestrator.prepare(plan.tasks[0])
    dispatch_id = cycle._dispatch_id(envelope)
    cycle.sessions.create(
        dispatch_id,
        envelope,
        baseline=ResponseBaseline.from_messages(("old",)),
        before_git_digest=None,
    )
    return plan, store, cycle, dispatch_id


def test_response_file_written_before_session_metadata_is_recovered_as_collected(tmp_path) -> None:
    _, store, cycle, dispatch_id = _cycle(tmp_path)
    cycle.sessions.update(dispatch_id, status="SUBMITTED")
    cycle.sessions.response_dir.mkdir(parents=True, exist_ok=True)
    orphan = cycle.sessions.response_dir / f"{dispatch_id}.txt"
    orphan.write_text("completed response", encoding="utf-8")

    controller = LocalRecoveryController(tmp_path, cycle)
    result = controller.reconcile_next()
    session = LocalSessionStore(tmp_path).get(dispatch_id)

    assert result.status == "RESUME"
    assert result.resumable is True
    assert session["status"] == "COLLECTED"
    assert session["response_digest"]
    assert session["response_path"].endswith(f"{dispatch_id}.txt")
    assert store.load()["tasks"]["task"]["attempts"] == 0
    event = ExecutionEvidenceLedger(tmp_path).latest_for_dispatch(dispatch_id)
    assert event is not None and event.kind == "RECOVERY_RESPONSE_FILE"


def test_workflow_pass_before_session_terminal_update_is_repaired_without_second_attempt(tmp_path) -> None:
    _, store, cycle, dispatch_id = _cycle(tmp_path)
    cycle.sessions.update(
        dispatch_id,
        status="CHECKED",
        check={
            "ok": True,
            "message": "checks passed",
            "failure_type": None,
            "returncode": 0,
        },
    )
    state = store.load()
    state["tasks"]["task"]["status"] = "PASSED"
    state["tasks"]["task"]["attempts"] = 1
    state["tasks"]["task"]["local_dispatch_id"] = dispatch_id
    state["status"] = "PASSED"
    state["current_task"] = None
    store.save(state)

    result = LocalRecoveryController(tmp_path, cycle).reconcile_next()
    session = LocalSessionStore(tmp_path).get(dispatch_id)
    state_after = store.load()

    assert result.status == "RECOVERED_STATE"
    assert result.safe_to_retry is False
    assert result.resumable is False
    assert session["status"] == "PASSED"
    assert state_after["tasks"]["task"]["attempts"] == 1
    event = ExecutionEvidenceLedger(tmp_path).latest_for_dispatch(dispatch_id)
    assert event is not None and event.kind == "RECOVERY_STATE_TERMINAL"


def test_recovery_of_terminal_state_is_idempotent(tmp_path) -> None:
    _, store, cycle, dispatch_id = _cycle(tmp_path)
    cycle.sessions.update(dispatch_id, status="CHECKED", check={"ok": True, "message": "ok"})
    state = store.load()
    state["tasks"]["task"]["status"] = "PASSED"
    state["tasks"]["task"]["attempts"] = 1
    state["tasks"]["task"]["local_dispatch_id"] = dispatch_id
    state["status"] = "PASSED"
    store.save(state)
    controller = LocalRecoveryController(tmp_path, cycle)

    first = controller.reconcile_next()
    second = controller.reconcile_next()

    assert first.status == "RECOVERED_STATE"
    assert second.status == "NO_TASK"
    assert store.load()["tasks"]["task"]["attempts"] == 1
    assert len(ExecutionEvidenceLedger(tmp_path).events_for_dispatch(dispatch_id)) == 1
