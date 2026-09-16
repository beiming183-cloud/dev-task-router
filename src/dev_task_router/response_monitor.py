from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Callable, Protocol


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest() if text else ""


@dataclass(frozen=True, slots=True)
class ResponseSnapshot:
    busy: bool
    messages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResponseBaseline:
    message_count: int
    latest_digest: str

    @classmethod
    def from_messages(cls, messages: tuple[str, ...]) -> "ResponseBaseline":
        latest = ConversationResponseMonitor._latest(messages)
        return cls(message_count=len(messages), latest_digest=_digest(latest))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResponseBaseline":
        return cls(
            message_count=max(0, int(data.get("message_count", 0))),
            latest_digest=str(data.get("latest_digest", "")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "message_count": self.message_count,
            "latest_digest": self.latest_digest,
        }


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

    def collect(
        self,
        baseline_messages: tuple[str, ...] = (),
        *,
        baseline: ResponseBaseline | None = None,
    ) -> ResponseCollectionResult:
        baseline = baseline or ResponseBaseline.from_messages(baseline_messages)
        started_at = self.clock()
        polls = 0
        saw_activity = False
        stable_text = ""
        stable_count = 0
        latest_seen = ""
        latest_is_new = False

        while True:
            snapshot = self.source.snapshot()
            polls += 1
            latest = self._latest(snapshot.messages)
            latest_seen = latest or latest_seen

            changed_from_baseline = bool(
                latest
                and (
                    len(snapshot.messages) > baseline.message_count
                    or _digest(latest) != baseline.latest_digest
                )
            )
            latest_is_new = changed_from_baseline
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
                    response_text=latest_seen if latest_is_new else "",
                    polls=polls,
                    saw_activity=saw_activity,
                    reason="response collection timed out before a stable new assistant response was verified",
                )

            self.sleeper(self.poll_interval_seconds)
