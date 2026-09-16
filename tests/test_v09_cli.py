from __future__ import annotations

import json

from dev_task_router.config import autodev_dir, load_plan, write_default_files
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.local_loop import LocalConversationOrchestrator
from dev_task_router.local_session import LocalSessionStore, LocalTaskCycle
from dev_task_router.loop_cli import main
from dev_task_router.models import Plan
from dev_task_router.response_monitor import (
    ConversationResponseMonitor,
    ResponseBaseline,
    ResponseSnapshot,
)
from dev_task_router.state import StateStore


class StaticSource:
    def snapshot(self) -> ResponseSnapshot:
        return ResponseSnapshot(False, ("old",))


def _project(tmp_path) -> Plan:
    write_default_files(tmp_path, "demo")
    plan = Plan.from_dict(
        {
            "version": 3,
            "project": "demo",
            "tasks": [
                {
                    "id": "feature",
                    "title": "Implement bounded feature",
                    "kind": "normal_code",
                    "prompt": "Implement bounded feature.",
                }
            ],
        }
    )
    (autodev_dir(tmp_path) / "plan.yaml").write_text(
        "version: 3\nproject: demo\ntasks:\n"
        "  - id: feature\n"
        "    title: Implement bounded feature\n"
        "    kind: normal_code\n"
        "    prompt: Implement bounded feature.\n",
        encoding="utf-8",
    )
    StateStore(tmp_path).create(load_plan(tmp_path))
    return plan


def test_evidence_cli_reports_valid_chain(tmp_path, capsys) -> None:
    _project(tmp_path)
    ledger = ExecutionEvidenceLedger(tmp_path)
    ledger.record(task_id="feature", dispatch_id="d1", kind="PREPARED")
    ledger.record(task_id="feature", dispatch_id="d1", kind="SUBMITTED")

    code = main(["--root", str(tmp_path), "evidence", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["chain_valid"] is True
    assert payload["event_count"] == 2
    assert [item["kind"] for item in payload["events"]] == ["PREPARED", "SUBMITTED"]


def test_recover_cli_marks_prepared_without_reservation_safe_to_retry(tmp_path, capsys) -> None:
    plan = _project(tmp_path)
    store = StateStore(tmp_path)
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
    LocalSessionStore(tmp_path).create(
        dispatch_id,
        envelope,
        baseline=ResponseBaseline.from_messages(("old",)),
        before_git_digest=None,
    )

    code = main(["--root", str(tmp_path), "recover", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "SAFE_RETRY"
    assert payload["safe_to_retry"] is True
    assert LocalSessionStore(tmp_path).get(dispatch_id)["status"] == "ABORTED_SAFE_RETRY"
