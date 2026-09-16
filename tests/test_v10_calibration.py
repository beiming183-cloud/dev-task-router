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
                {"attempt": 1, "level": "MEDIUM", "confidence": "medium"},
                {"attempt": 2, "level": "HIGH", "confidence": "high"},
            ],
        }
    )
    b = state["tasks"]["b"]
    b.update(
        {
            "status": "PASSED",
            "attempts": 1,
            "route_history": [
                {"attempt": 1, "level": "HIGH", "confidence": "medium"}
            ],
        }
    )
    c = state["tasks"]["c"]
    c.update(
        {
            "status": "FAILED",
            "attempts": 1,
            "route_history": [{"attempt": 1, "level": "NONE", "confidence": "high"}],
            "debug_task_required": True,
        }
    )
    store.save(state)

    usage = tmp_path / ".autodev" / "usage.jsonl"
    usage.write_text(
        json.dumps(
            {
                "task_id": "a",
                "level": "HIGH",
                "duration_seconds": 4.0,
                "input_tokens": 100,
                "output_tokens": 50,
            }
        )
        + "\n"
        + json.dumps(
            {
                "task_id": "b",
                "level": "HIGH",
                "duration_seconds": 2.5,
                "input_tokens": None,
                "output_tokens": None,
            }
        )
        + "\n"
        + json.dumps(
            {
                "task_id": "c",
                "level": "NONE",
                "duration_seconds": None,
                "input_tokens": None,
                "output_tokens": None,
            }
        )
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
    assert report.by_initial_level["MEDIUM"].average_attempts == 2.0
    assert report.by_initial_level["HIGH"].one_shot_passed == 1
    assert report.by_initial_level["HIGH"].one_shot_pass_rate == 1.0
    assert report.by_initial_level["HIGH"].duration_records == 2
    assert report.by_initial_level["HIGH"].duration_seconds == 6.5
    assert report.by_initial_level["HIGH"].average_duration_seconds == 3.25
    assert report.by_initial_level["HIGH"].token_records == 1
    assert report.by_initial_level["NONE"].failed == 1
    assert report.observed_terminal_duration_seconds == 3.0
    assert report.usage_record_count == 3
    assert report.duration_record_count == 2
    assert report.duration_coverage == 2 / 3
    assert report.observed_execution_duration_seconds == 6.5
    assert report.token_record_count == 1
    assert report.token_coverage == 1 / 3
    assert report.input_tokens == 100
    assert report.output_tokens == 50

    assert len(report.high_manual_review_candidates) == 1
    candidate = report.high_manual_review_candidates[0]
    assert candidate.task_id == "b"
    assert candidate.confidence == "medium"
    assert candidate.duration_seconds == 2.5
    assert "not evidence that a lower profile would have succeeded" in candidate.evidence
    assert report.to_dict()["policy_changed"] is False


def test_high_one_shot_candidate_does_not_modify_task_or_state(tmp_path) -> None:
    task = TaskSpec(
        id="high",
        title="Architecture change",
        prompt="Design architecture",
        kind="architecture",
        level=None,
    )
    plan = Plan(project="demo", tasks=[task])
    store = StateStore(tmp_path)
    state = store.ensure_for_plan(plan)
    state["tasks"]["high"].update(
        {
            "status": "PASSED",
            "attempts": 1,
            "route": {"level": "HIGH"},
            "route_history": [{"attempt": 1, "level": "HIGH", "confidence": "high"}],
        }
    )
    store.save(state)
    before = store.load()

    report = OutcomeCalibrator(tmp_path, plan, store).run()

    assert [item.task_id for item in report.high_manual_review_candidates] == ["high"]
    assert task.level is None
    assert store.load() == before
