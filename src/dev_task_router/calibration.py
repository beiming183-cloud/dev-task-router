from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .config import USAGE_FILE, autodev_dir
from .models import ModelLevel, Plan, TaskStatus
from .state import StateStore


@dataclass(frozen=True, slots=True)
class LevelOutcome:
    tasks: int = 0
    passed: int = 0
    failed: int = 0
    blocked: int = 0
    attempts: int = 0
    one_shot_passed: int = 0
    usage_records: int = 0
    duration_records: int = 0
    duration_seconds: float = 0.0
    token_records: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def pass_rate(self) -> float | None:
        return self.passed / self.tasks if self.tasks else None

    @property
    def one_shot_pass_rate(self) -> float | None:
        return self.one_shot_passed / self.tasks if self.tasks else None

    @property
    def average_attempts(self) -> float | None:
        return self.attempts / self.tasks if self.tasks else None

    @property
    def average_duration_seconds(self) -> float | None:
        return self.duration_seconds / self.duration_records if self.duration_records else None

    def to_dict(self) -> dict:
        return {
            "tasks": self.tasks,
            "passed": self.passed,
            "failed": self.failed,
            "blocked": self.blocked,
            "attempts": self.attempts,
            "one_shot_passed": self.one_shot_passed,
            "pass_rate": round(self.pass_rate, 4) if self.pass_rate is not None else None,
            "one_shot_pass_rate": (
                round(self.one_shot_pass_rate, 4)
                if self.one_shot_pass_rate is not None
                else None
            ),
            "average_attempts": (
                round(self.average_attempts, 3) if self.average_attempts is not None else None
            ),
            "usage_records": self.usage_records,
            "duration_records": self.duration_records,
            "duration_seconds": round(self.duration_seconds, 3),
            "average_duration_seconds": (
                round(self.average_duration_seconds, 3)
                if self.average_duration_seconds is not None
                else None
            ),
            "token_records": self.token_records,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
        }


@dataclass(frozen=True, slots=True)
class HighReviewCandidate:
    """A HIGH-first one-shot success worth controlled follow-up, not a downgrade verdict."""

    task_id: str
    title: str
    confidence: str | None
    duration_seconds: float | None
    evidence: str

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "confidence": self.confidence,
            "duration_seconds": (
                round(self.duration_seconds, 3) if self.duration_seconds is not None else None
            ),
            "evidence": self.evidence,
        }


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    task_count: int
    observed_task_count: int
    by_initial_level: dict[str, LevelOutcome]
    promotion_count: int
    high_first_route_count: int
    high_after_promotion_count: int
    deterministic_debug_required_count: int
    observed_terminal_duration_seconds: float
    usage_record_count: int
    duration_record_count: int
    observed_execution_duration_seconds: float
    token_record_count: int
    input_tokens: int
    output_tokens: int
    high_manual_review_candidates: tuple[HighReviewCandidate, ...]

    @property
    def duration_coverage(self) -> float | None:
        return self.duration_record_count / self.usage_record_count if self.usage_record_count else None

    @property
    def token_coverage(self) -> float | None:
        return self.token_record_count / self.usage_record_count if self.usage_record_count else None

    def to_dict(self) -> dict:
        return {
            "task_count": self.task_count,
            "observed_task_count": self.observed_task_count,
            "by_initial_level": {
                key: value.to_dict() for key, value in self.by_initial_level.items()
            },
            "promotion_count": self.promotion_count,
            "high_first_route_count": self.high_first_route_count,
            "high_after_promotion_count": self.high_after_promotion_count,
            "deterministic_debug_required_count": self.deterministic_debug_required_count,
            "observed_terminal_duration_seconds": round(
                self.observed_terminal_duration_seconds, 3
            ),
            "usage_record_count": self.usage_record_count,
            "duration_record_count": self.duration_record_count,
            "duration_coverage": (
                round(self.duration_coverage, 4) if self.duration_coverage is not None else None
            ),
            "observed_execution_duration_seconds": round(
                self.observed_execution_duration_seconds, 3
            ),
            "token_record_count": self.token_record_count,
            "token_coverage": (
                round(self.token_coverage, 4) if self.token_coverage is not None else None
            ),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "high_manual_review_candidate_count": len(self.high_manual_review_candidates),
            "high_manual_review_candidates": [
                item.to_dict() for item in self.high_manual_review_candidates
            ],
            "policy_changed": False,
        }


def _duration_seconds(started: str | None, finished: str | None) -> float:
    if not started or not finished:
        return 0.0
    try:
        return max(0.0, (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds())
    except (TypeError, ValueError):
        return 0.0


def _usage_records(root: Path) -> list[dict]:
    path = autodev_dir(root) / USAGE_FILE
    if not path.exists():
        return []
    records: list[dict] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            records.append(item)
    return records


def _usage_duration(row: dict) -> float | None:
    value = row.get("duration_seconds")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
        return float(value)
    return None


def _usage_token(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


class OutcomeCalibrator:
    """Summarize observed routing outcomes without auto-changing routing policy.

    The report is descriptive evidence. V1.0 deliberately does not lower HIGH or
    rewrite thresholds from a small sample automatically. A HIGH one-shot success is
    only a candidate for later controlled lower-profile comparison; it is not proof
    that MEDIUM or LOW would have succeeded. Reporting is read-only and never advances
    workflow timestamps or initializes missing Task state.
    """

    def __init__(self, root: Path, plan: Plan, store: StateStore):
        self.root = root
        self.plan = plan
        self.store = store

    def _read_state(self) -> dict:
        if not self.store.exists():
            return {"project": self.plan.project, "tasks": {}}
        state = self.store.load()
        if state.get("project") != self.plan.project:
            raise ValueError("state project does not match plan project")
        tasks = state.get("tasks")
        if not isinstance(tasks, dict):
            raise ValueError("state must contain a tasks mapping")
        expected = {task.id for task in self.plan.tasks}
        removed = set(tasks) - expected
        if removed:
            raise ValueError(
                "plan removed tasks after state creation; refusing to ignore durable task state: "
                + ", ".join(sorted(removed))
            )
        return state

    def run(self) -> CalibrationReport:
        state = self._read_state()
        durable_tasks = state.get("tasks", {})
        mutable = {
            level.value: {
                "tasks": 0,
                "passed": 0,
                "failed": 0,
                "blocked": 0,
                "attempts": 0,
                "one_shot_passed": 0,
                "usage_records": 0,
                "duration_records": 0,
                "duration_seconds": 0.0,
                "token_records": 0,
                "input_tokens": 0,
                "output_tokens": 0,
            }
            for level in ModelLevel
        }
        observed = 0
        promotions = 0
        high_first = 0
        high_after = 0
        debug_required = 0
        terminal_duration = 0.0
        high_candidates: list[HighReviewCandidate] = []

        usage = _usage_records(self.root)
        usage_by_task: dict[str, list[dict]] = {}
        duration_record_count = 0
        execution_duration = 0.0
        token_records = 0
        input_tokens = 0
        output_tokens = 0

        for row in usage:
            task_id = str(row.get("task_id") or "").strip()
            if task_id:
                usage_by_task.setdefault(task_id, []).append(row)
            raw_level = str(row.get("level") or "").upper()
            bucket = mutable.get(raw_level)
            if bucket is not None:
                bucket["usage_records"] += 1

            duration = _usage_duration(row)
            if duration is not None:
                duration_record_count += 1
                execution_duration += duration
                if bucket is not None:
                    bucket["duration_records"] += 1
                    bucket["duration_seconds"] += duration

            in_tok = _usage_token(row.get("input_tokens"))
            out_tok = _usage_token(row.get("output_tokens"))
            if in_tok is not None or out_tok is not None:
                token_records += 1
                if bucket is not None:
                    bucket["token_records"] += 1
            if in_tok is not None:
                input_tokens += in_tok
                if bucket is not None:
                    bucket["input_tokens"] += in_tok
            if out_tok is not None:
                output_tokens += out_tok
                if bucket is not None:
                    bucket["output_tokens"] += out_tok

        for task in self.plan.tasks:
            item = durable_tasks.get(task.id)
            if not isinstance(item, dict):
                continue
            history = item.get("route_history") or []
            if not history:
                continue
            observed += 1
            levels = [str(row.get("level", "")) for row in history if row.get("level")]
            initial = levels[0] if levels else str(item.get("route", {}).get("level") or "")
            if initial not in mutable:
                continue

            bucket = mutable[initial]
            bucket["tasks"] += 1
            attempts = int(item.get("attempts", 0))
            bucket["attempts"] += attempts
            status = str(item.get("status", ""))
            if status == TaskStatus.PASSED.value:
                bucket["passed"] += 1
                if attempts == 1:
                    bucket["one_shot_passed"] += 1
            elif status == TaskStatus.FAILED.value:
                bucket["failed"] += 1
            elif status == TaskStatus.BLOCKED.value:
                bucket["blocked"] += 1

            distinct_levels: list[str] = []
            for level in levels:
                if not distinct_levels or distinct_levels[-1] != level:
                    distinct_levels.append(level)
            if len(distinct_levels) > 1:
                promotions += len(distinct_levels) - 1
            if initial == ModelLevel.HIGH.value:
                high_first += 1
            elif levels and levels[-1] == ModelLevel.HIGH.value:
                high_after += 1
            if item.get("debug_task_required"):
                debug_required += 1
            terminal_duration += _duration_seconds(item.get("started_at"), item.get("finished_at"))

            if initial == ModelLevel.HIGH.value and status == TaskStatus.PASSED.value and attempts == 1:
                initial_row = history[0] if isinstance(history[0], dict) else {}
                confidence = str(initial_row.get("confidence") or "").strip() or None
                durations = [
                    value
                    for value in (_usage_duration(row) for row in usage_by_task.get(task.id, []))
                    if value is not None
                ]
                high_candidates.append(
                    HighReviewCandidate(
                        task_id=task.id,
                        title=task.title,
                        confidence=confidence,
                        duration_seconds=sum(durations) if durations else None,
                        evidence=(
                            "HIGH was the first route and the Task passed in one implementation attempt; "
                            "this is only a candidate for a future controlled lower-profile comparison, "
                            "not evidence that a lower profile would have succeeded"
                        ),
                    )
                )

        return CalibrationReport(
            task_count=len(self.plan.tasks),
            observed_task_count=observed,
            by_initial_level={
                key: LevelOutcome(**value) for key, value in mutable.items()
            },
            promotion_count=promotions,
            high_first_route_count=high_first,
            high_after_promotion_count=high_after,
            deterministic_debug_required_count=debug_required,
            observed_terminal_duration_seconds=terminal_duration,
            usage_record_count=len(usage),
            duration_record_count=duration_record_count,
            observed_execution_duration_seconds=execution_duration,
            token_record_count=token_records,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            high_manual_review_candidates=tuple(high_candidates),
        )
