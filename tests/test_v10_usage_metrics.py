from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from dev_task_router.calibration import OutcomeCalibrator
from dev_task_router.e2e_calibration import EndToEndCalibrationRecorder
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.local_project_loop import LocalProjectLoop
from dev_task_router.local_session import LocalCycleResult
from dev_task_router.models import Plan, TaskSpec
from dev_task_router.state import StateStore
from dev_task_router.usage import UsageLogger


def _usage_rows(root):
    path = root / ".autodev" / "usage.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_usage_logger_is_idempotent_and_does_not_invent_tokens(tmp_path) -> None:
    logger = UsageLogger(tmp_path)
    route = {
        "level": "HIGH",
        "provider": "chatgpt",
        "model": "sol",
        "executor": "local-conversation",
        "reason": "observed route",
    }

    first = logger.append(
        task_id="t1",
        route=route,
        status="PASSED",
        returncode=0,
        attempt=1,
        duration_seconds=3.25,
        dispatch_id="dispatch-1",
        source="local-conversation",
        usage_id="dispatch:dispatch-1:final",
    )
    replay = logger.append(
        task_id="t1",
        route=route,
        status="PASSED",
        returncode=0,
        attempt=1,
        duration_seconds=99.0,
        input_tokens=999,
        output_tokens=999,
        dispatch_id="dispatch-1",
        source="local-conversation",
        usage_id="dispatch:dispatch-1:final",
    )

    assert first is True
    assert replay is False
    rows = _usage_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["duration_seconds"] == 3.25
    assert rows[0]["input_tokens"] is None
    assert rows[0]["output_tokens"] is None


def test_usage_logger_accepts_only_reported_non_negative_tokens(tmp_path) -> None:
    logger = UsageLogger(tmp_path)
    route = {"level": "MEDIUM"}
    assert logger.append(
        task_id="t",
        route=route,
        status="PASSED",
        returncode=0,
        input_tokens=12,
        output_tokens=7,
        usage_id="real-token-record",
    )
    with pytest.raises(ValueError, match="input_tokens"):
        logger.append(
            task_id="bad-negative",
            route=route,
            status="PASSED",
            returncode=0,
            input_tokens=-1,
        )
    with pytest.raises(ValueError, match="input_tokens"):
        logger.append(
            task_id="bad-bool",
            route=route,
            status="PASSED",
            returncode=0,
            input_tokens=True,
        )
    with pytest.raises(ValueError, match="output_tokens"):
        logger.append(
            task_id="bad-output-bool",
            route=route,
            status="PASSED",
            returncode=0,
            output_tokens=False,
        )

    rows = _usage_rows(tmp_path)
    assert rows[0]["input_tokens"] == 12
    assert rows[0]["output_tokens"] == 7


def test_usage_logger_rejects_bool_and_negative_duration(tmp_path) -> None:
    logger = UsageLogger(tmp_path)
    route = {"level": "LOW"}
    with pytest.raises(ValueError, match="duration_seconds"):
        logger.append(
            task_id="bool-duration",
            route=route,
            status="PASSED",
            returncode=0,
            duration_seconds=True,
        )
    with pytest.raises(ValueError, match="duration_seconds"):
        logger.append(
            task_id="negative-duration",
            route=route,
            status="PASSED",
            returncode=0,
            duration_seconds=-0.1,
        )
    assert _usage_rows(tmp_path) == []


def test_calibration_ignores_malformed_manual_token_values(tmp_path) -> None:
    task = TaskSpec(id="t", title="Task", prompt="Implement feature")
    plan = Plan(project="demo", tasks=[task])
    store = StateStore(tmp_path)
    state = store.ensure_for_plan(plan)
    state["tasks"]["t"].update(
        {
            "status": "PASSED",
            "attempts": 1,
            "route": {"level": "MEDIUM"},
            "route_history": [{"attempt": 1, "level": "MEDIUM"}],
        }
    )
    store.save(state)
    path = tmp_path / ".autodev" / "usage.jsonl"
    path.write_text(
        json.dumps(
            {
                "task_id": "t",
                "level": "MEDIUM",
                "input_tokens": True,
                "output_tokens": -7,
                "duration_seconds": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = OutcomeCalibrator(tmp_path, plan, store).run()
    assert report.usage_record_count == 1
    assert report.token_record_count == 0
    assert report.input_tokens == 0
    assert report.output_tokens == 0
    assert report.duration_record_count == 0
    assert report.observed_execution_duration_seconds == 0.0


class _Sessions:
    def __init__(self, item):
        self.item = item

    def get(self, dispatch_id):
        return self.item if dispatch_id == "d1" else None


class _Cycle:
    def __init__(self, sessions, evidence):
        self.sessions = sessions
        self.evidence = evidence


def test_model_terminal_usage_is_recorded_once_per_dispatch(tmp_path) -> None:
    task = TaskSpec(id="model", title="Model task", prompt="Implement feature")
    plan = Plan(project="demo", tasks=[task])
    store = StateStore(tmp_path)
    state = store.ensure_for_plan(plan)
    state["tasks"]["model"].update(
        {
            "status": "PASSED",
            "attempts": 1,
            "route": {
                "level": "MEDIUM",
                "provider": "chatgpt",
                "model": "sol",
                "executor": "local-conversation",
                "reason": "normal implementation",
            },
            "route_history": [{"attempt": 1, "level": "MEDIUM"}],
        }
    )
    store.save(state)
    created = (datetime.now(timezone.utc) - timedelta(seconds=2)).isoformat()
    sessions = _Sessions(
        {
            "task_id": "model",
            "created_at": created,
            "check": {"ok": True, "returncode": 0},
        }
    )
    evidence = ExecutionEvidenceLedger(tmp_path)
    cycle = _Cycle(sessions, evidence)
    loop = LocalProjectLoop(
        tmp_path,
        plan,
        store,
        cycle,
        e2e_calibration=EndToEndCalibrationRecorder(
            tmp_path, evidence=evidence, sessions=sessions
        ),
    )
    result = LocalCycleResult(
        task_id="model",
        status="PASSED",
        dispatch_id="d1",
        infrastructure_failure=False,
        message="passed",
    )

    loop._record_model_usage(result)
    loop._record_model_usage(result)

    rows = _usage_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["usage_id"] == "dispatch:d1:final"
    assert rows[0]["level"] == "MEDIUM"
    assert rows[0]["duration_seconds"] >= 1.0
    assert rows[0]["input_tokens"] is None
    assert rows[0]["output_tokens"] is None
