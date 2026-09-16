from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Protocol


@dataclass(frozen=True, slots=True)
class ResponseSnapshot:
    busy: bool
    messages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResponseCollectionResult:
    completed: bool
    response_text: str
    polls: int
    saw_activity: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "completed": self.completed,
            "response_text": self.response_text,
            "polls": self.polls,
            "saw_activity": self.saw_activity,
            "reason": self.reason,
        }


class ResponseSnapshotSource(Protocol):
    def snapshot(self) -> ResponseSnapshot: ...


class ConversationResponseMonitor:
    """Detect response completion from calibrated UI snapshots.

    The monitor does not interpret assistant content as Task success. It only decides
    whether a new assistant response appears to have stopped changing. Callers must
    still run Checker/Git verification after collection.
    """

    def __init__(
        self,
        source: ResponseSnapshotSource,
        *,
        poll_interval_seconds: float = 1.0,
        timeout_seconds: float = 900.0,
        stable_polls: int = 2,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ):
        if poll_interval_seconds <= 0:
            raise ValueError("response poll_interval_seconds must be > 0")
        if timeout_seconds <= 0:
            raise ValueError("response timeout_seconds must be > 0")
        if stable_polls < 1:
            raise ValueError("response stable_polls must be >= 1")
        self.source = source
        self.poll_interval_seconds = poll_interval_seconds
        self.timeout_seconds = timeout_seconds
        self.stable_polls = stable_polls
        self.clock = clock
        self.sleeper = sleeper

    @staticmethod
    def _latest(messages: tuple[str, ...]) -> str:
        for message in reversed(messages):
            text = message.strip()
            if text:
                return text
        return ""

    def collect(self, baseline_messages: tuple[str, ...] = ()) -> ResponseCollectionResult:
        baseline_latest = self._latest(baseline_messages)
        started_at = self.clock()
        polls = 0
        saw_activity = False
        stable_text = ""
        stable_count = 0
        latest_seen = ""

        while True:
            snapshot = self.source.snapshot()
            polls += 1
            latest = self._latest(snapshot.messages)
            latest_seen = latest or latest_seen

            changed_from_baseline = bool(latest and latest != baseline_latest)
            if snapshot.busy or changed_from_baseline:
                saw_activity = True

            if saw_activity and changed_from_baseline and not snapshot.busy:
                if latest == stable_text:
                    stable_count += 1
                else:
                    stable_text = latest
                    stable_count = 1
                if stable_count >= self.stable_polls:
                    return ResponseCollectionResult(
                        completed=True,
                        response_text=latest,
                        polls=polls,
                        saw_activity=True,
                        reason=(
                            f"new assistant response remained stable for {self.stable_polls} poll(s) "
                            "with no busy indicator"
                        ),
                    )
            else:
                stable_text = ""
                stable_count = 0

            if self.clock() - started_at >= self.timeout_seconds:
                return ResponseCollectionResult(
                    completed=False,
                    response_text=latest_seen if changed_from_baseline else "",
                    polls=polls,
                    saw_activity=saw_activity,
                    reason="response collection timed out before a stable new assistant response was verified",
                )

            self.sleeper(self.poll_interval_seconds)
