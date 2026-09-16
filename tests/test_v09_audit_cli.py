from __future__ import annotations

import json

from dev_task_router.config import autodev_dir, write_default_files
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.loop_cli import main
from dev_task_router.models import Plan
from dev_task_router.state import StateStore


def _project(tmp_path) -> None:
    plan = Plan.from_dict(
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
    write_default_files(tmp_path, plan.project)
    StateStore(tmp_path).create(plan)


def test_audit_cli_succeeds_on_clean_empty_runtime(tmp_path, capsys) -> None:
    _project(tmp_path)

    code = main(["--root", str(tmp_path), "audit", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["error_count"] == 0


def test_audit_cli_returns_nonzero_for_corrupt_evidence_chain(tmp_path, capsys) -> None:
    _project(tmp_path)
    ledger = ExecutionEvidenceLedger(tmp_path)
    ledger.record(task_id="task", dispatch_id="d1", kind="PREPARED")
    row = json.loads(ledger.path.read_text(encoding="utf-8"))
    row["record_hash"] = "tampered"
    ledger.path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    code = main(["--root", str(tmp_path), "audit", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 1
    assert payload["ok"] is False
    assert "EVIDENCE_CHAIN_INVALID" in {item["code"] for item in payload["issues"]}


def test_audit_cli_warning_does_not_fail_exit_code(tmp_path, capsys) -> None:
    _project(tmp_path)
    sessions = {
        "version": 1,
        "sessions": {
            "d1": {
                "task_id": "task",
                "status": "PREPARED",
                "baseline": {"message_count": 1, "latest_digest": "old"},
            }
        },
    }
    (autodev_dir(tmp_path) / "local-sessions.json").write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    code = main(["--root", str(tmp_path), "audit", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["ok"] is True
    assert payload["warning_count"] == 1
    assert payload["issues"][0]["code"] == "SAFE_RETRY_AVAILABLE"
