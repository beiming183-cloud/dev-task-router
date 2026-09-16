from __future__ import annotations

import hashlib
import json

from dev_task_router.config import autodev_dir, write_default_files
from dev_task_router.execution_audit import LocalExecutionAuditor
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.models import Plan
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


def _base(tmp_path):
    plan = _plan()
    write_default_files(tmp_path, plan.project)
    store = StateStore(tmp_path)
    store.create(plan)
    return plan, store


def _write_json(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clean_model_state(tmp_path):
    plan, store = _base(tmp_path)
    dispatch_id = "d1"
    response = "verified assistant response"
    response_path = autodev_dir(tmp_path) / "local-responses" / f"{dispatch_id}.txt"
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(response, encoding="utf-8")
    digest = hashlib.sha256(response.encode("utf-8")).hexdigest()

    _write_json(
        autodev_dir(tmp_path) / "local-sessions.json",
        {
            "version": 1,
            "sessions": {
                dispatch_id: {
                    "task_id": "task",
                    "status": "PASSED",
                    "response_path": response_path.relative_to(tmp_path).as_posix(),
                    "response_digest": digest,
                    "check": {
                        "ok": True,
                        "message": "checks passed",
                        "failure_type": None,
                        "returncode": 0,
                    },
                }
            },
        },
    )
    _write_json(
        autodev_dir(tmp_path) / "local-dispatch.json",
        {
            "version": 1,
            "entries": {
                dispatch_id: {
                    "task_id": "task",
                    "status": "submitted",
                }
            },
        },
    )
    state = store.load()
    state["tasks"]["task"]["status"] = "PASSED"
    state["tasks"]["task"]["attempts"] = 1
    state["tasks"]["task"]["local_dispatch_id"] = dispatch_id
    state["status"] = "PASSED"
    store.save(state)

    evidence = ExecutionEvidenceLedger(tmp_path)
    evidence.record(task_id="task", dispatch_id=dispatch_id, kind="PREPARED")
    evidence.record(task_id="task", dispatch_id=dispatch_id, kind="SUBMITTED")
    evidence.record(
        task_id="task",
        dispatch_id=dispatch_id,
        kind="STATE_RECORDED",
        data={
            "task_status": "PASSED",
            "attempts": 1,
            "workflow_status": "PASSED",
        },
    )
    return plan, store, dispatch_id, response_path


def test_clean_model_runtime_state_passes_audit(tmp_path) -> None:
    _clean_model_state(tmp_path)

    report = LocalExecutionAuditor(tmp_path).run()

    assert report.ok is True
    assert report.errors == ()
    assert report.warnings == ()
    assert report.session_count == 1
    assert report.dispatch_count == 1


def test_response_digest_tamper_is_an_audit_error(tmp_path) -> None:
    _, _, _, response_path = _clean_model_state(tmp_path)
    response_path.write_text("tampered response", encoding="utf-8")

    report = LocalExecutionAuditor(tmp_path).run()

    assert report.ok is False
    assert "RESPONSE_DIGEST_MISMATCH" in {issue.code for issue in report.errors}


def test_prepared_without_reservation_is_recoverable_warning_not_corruption(tmp_path) -> None:
    _, _ = _base(tmp_path)
    _write_json(
        autodev_dir(tmp_path) / "local-sessions.json",
        {
            "version": 1,
            "sessions": {
                "d1": {
                    "task_id": "task",
                    "status": "PREPARED",
                    "baseline": {"message_count": 1, "latest_digest": "old"},
                }
            },
        },
    )

    report = LocalExecutionAuditor(tmp_path).run()

    assert report.ok is True
    assert "SAFE_RETRY_AVAILABLE" in {issue.code for issue in report.warnings}


def test_missing_state_evidence_is_sync_warning_and_not_second_attempt(tmp_path) -> None:
    _, store, dispatch_id, _ = _clean_model_state(tmp_path)
    evidence_path = ExecutionEvidenceLedger(tmp_path).path
    evidence_path.unlink()
    ExecutionEvidenceLedger(tmp_path).record(
        task_id="task",
        dispatch_id=dispatch_id,
        kind="PREPARED",
    )
    before_attempts = store.load()["tasks"]["task"]["attempts"]

    report = LocalExecutionAuditor(tmp_path).run()
    after_attempts = store.load()["tasks"]["task"]["attempts"]

    assert report.ok is True
    assert "EVIDENCE_SYNC_PENDING" in {issue.code for issue in report.warnings}
    assert before_attempts == after_attempts == 1


def test_invalid_evidence_chain_fails_audit(tmp_path) -> None:
    _base(tmp_path)
    ledger = ExecutionEvidenceLedger(tmp_path)
    ledger.record(task_id="task", dispatch_id="d1", kind="PREPARED")
    row = json.loads(ledger.path.read_text(encoding="utf-8"))
    row["record_hash"] = "broken"
    ledger.path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    report = LocalExecutionAuditor(tmp_path).run()

    assert report.ok is False
    assert "EVIDENCE_CHAIN_INVALID" in {issue.code for issue in report.errors}
