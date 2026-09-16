from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from dev_task_router.calibration import OutcomeCalibrator
from dev_task_router.models import Plan, TaskSpec
from dev_task_router.state import StateStore


def test_calibration_summarizes_promotions_and_usage_without_changing_policy(tmp_path) -> None:
    tasks = [
        TaskSpec(id="a", title="Implement feature", prompt="Implement feature", kind="normal_code"),
        TaskSpec(id="b", title="Fix hard bug", prompt="Investigate root cause", kind="normal_debug"),
        TaskSpec(id="c", title="Run tests", command=["pytest"], kind="test"),
    ]
    plan = Plan(project="demo", tasks=tasks)
    store = StateStore(tmp_path)
    state = store.ensure_for_plan(plan)

    now = datetime.now(timezone.utc)
    a = state["tasks"]["a"]
    a.update(
        {
            "status": "PASSED",
            "attempts": 2,
            "started_at": now.isoformat(),
            "finished_at": (now + timedelta(seconds=3)).isoformat(),
            "route_history": [
                {"attempt": 1, "level": "MEDIUM"},
                {"attempt": 2, "level": "HIGH"},
            ],
        }
    )
    b = state["tasks"]["b"]
    b.update(
        {
            "status": "PASSED",
            "attempts": 1,
            "route_history": [{"attempt": 1, "level": "HIGH"}],
        }
    )
    c = state["tasks"]["c"]
    c.update(
        {
            "status": "FAILED",
            "attempts": 1,
            "route_history": [{"attempt": 1, "level": "NONE"}],
            "debug_task_required": True,
        }
    )
    store.save(state)

    usage = tmp_path / ".autodev" / "usage.jsonl"
    usage.write_text(
        json.dumps({"task_id": "a", "input_tokens": 100, "output_tokens": 50}) + "\n"
        + json.dumps({"task_id": "b", "input_tokens": None, "output_tokens": None})
        + "\n",
        encoding="utf-8",
    )

    report = OutcomeCalibrator(tmp_path, plan, store).run()
    assert report.observed_task_count == 3
    assert report.promotion_count == 1
    assert report.high_first_route_count == 1
    assert report.high_after_promotion_count == 1
    assert report.deterministic_debug_required_count == 1
    assert report.by_initial_level["MEDIUM"].passed == 1
    assert report.by_initial_level["NONE"].failed == 1
    assert report.observed_terminal_duration_seconds == 3.0
    assert report.usage_record_count == 2
    assert report.token_record_count == 1
    assert report.input_tokens == 100
    assert report.output_tokens == 50
