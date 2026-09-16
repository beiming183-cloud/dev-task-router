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

    def to_dict(self) -> dict:
        return {
            "tasks": self.tasks,
            "passed": self.passed,
            "failed": self.failed,
            "blocked": self.blocked,
            "attempts": self.attempts,
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
    token_record_count: int
    input_tokens: int
    output_tokens: int

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
            "token_record_count": self.token_record_count,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
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


class OutcomeCalibrator:
    """Summarize observed routing outcomes without auto-changing routing policy.

    The report is descriptive evidence. V1.0 deliberately does not lower HIGH or
    rewrite thresholds from a small sample automatically.
    """

    def __init__(self, root: Path, plan: Plan, store: StateStore):
        self.root = root
        self.plan = plan
        self.store = store

    def run(self) -> CalibrationReport:
        state = self.store.ensure_for_plan(self.plan)
        mutable = {
            level.value: {"tasks": 0, "passed": 0, "failed": 0, "blocked": 0, "attempts": 0}
            for level in ModelLevel
        }
        observed = 0
        promotions = 0
        high_first = 0
        high_after = 0
        debug_required = 0
        duration = 0.0

        for task in self.plan.tasks:
            item = state["tasks"][task.id]
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
            bucket["attempts"] += int(item.get("attempts", 0))
            status = str(item.get("status", ""))
            if status == TaskStatus.PASSED.value:
                bucket["passed"] += 1
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
            duration += _duration_seconds(item.get("started_at"), item.get("finished_at"))

        usage = _usage_records(self.root)
        token_records = 0
        input_tokens = 0
        output_tokens = 0
        for row in usage:
            in_tok = row.get("input_tokens")
            out_tok = row.get("output_tokens")
            if isinstance(in_tok, int) or isinstance(out_tok, int):
                token_records += 1
            if isinstance(in_tok, int):
                input_tokens += in_tok
            if isinstance(out_tok, int):
                output_tokens += out_tok

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
            observed_terminal_duration_seconds=duration,
            usage_record_count=len(usage),
            token_record_count=token_records,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
