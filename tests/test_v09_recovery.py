from __future__ import annotations

from dataclasses import dataclass

from dev_task_router.config import write_default_files
from dev_task_router.conversation_ui import DispatchLedger
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.local_loop import LocalConversationOrchestrator
from dev_task_router.local_session import LocalTaskCycle
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
                    "prompt": "Implement the feature.",
                }
            ],
        }
    )


@dataclass
class StaticSource:
    value: ResponseSnapshot

    def snapshot(self) -> ResponseSnapshot:
        return self.value


def _setup(tmp_path, snapshot: ResponseSnapshot):
    plan = _plan()
    write_default_files(tmp_path, plan.project)
    store = StateStore(tmp_path)
    store.create(plan)
    orchestrator = LocalConversationOrchestrator(tmp_path, plan, store)
    monitor = ConversationResponseMonitor(
        StaticSource(snapshot),
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


def test_prepared_without_dispatch_reservation_is_safe_to_retry(tmp_path) -> None:
    _, _, cycle, dispatch_id = _setup(tmp_path, ResponseSnapshot(False, ("old",)))
    controller = LocalRecoveryController(tmp_path, cycle)

    result = controller.reconcile_next()

    assert result.status == "SAFE_RETRY"
    assert result.safe_to_retry is True
    assert result.resumable is False
    assert cycle.sessions.get(dispatch_id)["status"] == "ABORTED_SAFE_RETRY"
    assert cycle.sessions.active_for_task("task") is None
    events = ExecutionEvidenceLedger(tmp_path).events_for_dispatch(dispatch_id)
    assert [event.kind for event in events] == ["RECOVERY_SAFE_RETRY"]


def test_prepared_with_submitted_ledger_resumes_without_resend(tmp_path) -> None:
    _, _, cycle, dispatch_id = _setup(tmp_path, ResponseSnapshot(False, ("old",)))
    ledger = DispatchLedger(tmp_path)
    ledger.reserve(dispatch_id, "task")
    ledger.mark_submitted(dispatch_id)
    controller = LocalRecoveryController(tmp_path, cycle, dispatch_ledger=ledger)

    result = controller.reconcile_next()

    assert result.status == "RESUME"
    assert result.resumable is True
    assert result.safe_to_retry is False
    assert cycle.sessions.get(dispatch_id)["status"] == "SUBMITTED"
    assert ledger.get(dispatch_id)["status"] == "submitted"


def test_submitting_with_post_baseline_activity_is_promoted_to_submitted(tmp_path) -> None:
    _, _, cycle, dispatch_id = _setup(
        tmp_path,
        ResponseSnapshot(False, ("old", "new assistant output")),
    )
    ledger = DispatchLedger(tmp_path)
    ledger.reserve(dispatch_id, "task")
    controller = LocalRecoveryController(tmp_path, cycle, dispatch_ledger=ledger)

    result = controller.reconcile_next()

    assert result.status == "RESUME"
    assert result.resumable is True
    assert cycle.sessions.get(dispatch_id)["status"] == "SUBMITTED"
    assert ledger.get(dispatch_id)["status"] == "submitted"
    event = ExecutionEvidenceLedger(tmp_path).latest_for_dispatch(dispatch_id)
    assert event is not None
    assert event.kind == "RECOVERY_SUBMITTED"
    assert event.data["reason"] == "response_ui_activity"


def test_submitting_without_activity_remains_ambiguous_and_blocks_retry(tmp_path) -> None:
    _, _, cycle, dispatch_id = _setup(tmp_path, ResponseSnapshot(False, ("old",)))
    ledger = DispatchLedger(tmp_path)
    ledger.reserve(dispatch_id, "task")
    controller = LocalRecoveryController(tmp_path, cycle, dispatch_ledger=ledger)

    result = controller.reconcile_next()

    assert result.status == "AMBIGUOUS"
    assert result.resumable is False
    assert result.safe_to_retry is False
    assert cycle.sessions.get(dispatch_id)["status"] == "PREPARED"
    assert ledger.get(dispatch_id)["status"] == "submitting"


def test_busy_indicator_is_enough_to_prove_conversation_advanced(tmp_path) -> None:
    _, _, cycle, dispatch_id = _setup(tmp_path, ResponseSnapshot(True, ("old",)))
    ledger = DispatchLedger(tmp_path)
    ledger.reserve(dispatch_id, "task")
    controller = LocalRecoveryController(tmp_path, cycle, dispatch_ledger=ledger)

    result = controller.reconcile_next()

    assert result.status == "RESUME"
    assert ledger.get(dispatch_id)["status"] == "submitted"
