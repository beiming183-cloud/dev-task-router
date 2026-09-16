from __future__ import annotations

from dataclasses import dataclass

from dev_task_router.config import write_default_files
from dev_task_router.conversation_ui import DispatchLedger
from dev_task_router.evidence_cycle import EvidenceTrackingCycle
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.local_loop import LocalConversationOrchestrator
from dev_task_router.local_session import LocalTaskCycle
from dev_task_router.models import Plan
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
                }
            ],
        }
    )


@dataclass
class StaticSource:
    def snapshot(self) -> ResponseSnapshot:
        return ResponseSnapshot(False, ("old",))


def test_sync_reconstructs_compact_evidence_without_duplicate_rows(tmp_path) -> None:
    plan = _plan()
    write_default_files(tmp_path, plan.project)
    store = StateStore(tmp_path)
    store.create(plan)
    orchestrator = LocalConversationOrchestrator(tmp_path, plan, store)
    monitor = ConversationResponseMonitor(
        StaticSource(),
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
        before_git_digest="before",
    )
    dispatch = DispatchLedger(tmp_path)
    dispatch.reserve(dispatch_id, "task")
    dispatch.mark_submitted(dispatch_id)
    cycle.sessions.update(
        dispatch_id,
        status="SUBMITTED",
        dispatch_backend="fake-conversation",
    )
    secret_response = "assistant body stays in the response file, not evidence jsonl"
    cycle.sessions.save_response(dispatch_id, secret_response)
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
    state["tasks"]["task"]["local_dispatch_id"] = dispatch_id
    state["tasks"]["task"]["status"] = "PASSED"
    state["tasks"]["task"]["attempts"] = 1
    state["status"] = "PASSED"
    store.save(state)

    tracked = EvidenceTrackingCycle(tmp_path, cycle, dispatch_ledger=dispatch)
    tracked.sync_dispatch(dispatch_id)
    first_events = ExecutionEvidenceLedger(tmp_path).events_for_dispatch(dispatch_id)
    tracked.sync_dispatch(dispatch_id)
    second_events = ExecutionEvidenceLedger(tmp_path).events_for_dispatch(dispatch_id)

    assert [event.kind for event in first_events] == [
        "PREPARED",
        "SUBMITTED",
        "RESPONSE_COLLECTED",
        "CHECKED",
        "STATE_RECORDED",
        "SESSION_STATUS",
    ]
    assert len(second_events) == len(first_events)
    evidence_text = ExecutionEvidenceLedger(tmp_path).path.read_text(encoding="utf-8")
    assert secret_response not in evidence_text
    assert first_events[2].data["response_chars"] == len(secret_response)
    assert first_events[4].data["task_status"] == "PASSED"
