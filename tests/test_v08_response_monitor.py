from __future__ import annotations

from dataclasses import dataclass

from dev_task_router.response_monitor import (
    ConversationResponseMonitor,
    ResponseBaseline,
    ResponseSnapshot,
)


@dataclass
class SequenceSource:
    snapshots: list[ResponseSnapshot]
    index: int = 0

    def snapshot(self) -> ResponseSnapshot:
        if self.index >= len(self.snapshots):
            return self.snapshots[-1]
        value = self.snapshots[self.index]
        self.index += 1
        return value


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _monitor(source: SequenceSource, *, timeout: float = 10.0, stable: int = 2):
    clock = FakeClock()
    return ConversationResponseMonitor(
        source,
        poll_interval_seconds=1.0,
        timeout_seconds=timeout,
        stable_polls=stable,
        clock=clock.now,
        sleeper=clock.sleep,
    )


def test_busy_then_stable_new_response_completes() -> None:
    source = SequenceSource(
        [
            ResponseSnapshot(True, ("old",)),
            ResponseSnapshot(True, ("old", "working")),
            ResponseSnapshot(False, ("old", "done")),
            ResponseSnapshot(False, ("old", "done")),
        ]
    )

    result = _monitor(source).collect(("old",))

    assert result.completed is True
    assert result.response_text == "done"
    assert result.saw_activity is True
    assert result.polls == 5


def test_streaming_text_change_resets_stable_counter() -> None:
    source = SequenceSource(
        [
            ResponseSnapshot(False, ("old", "part 1")),
            ResponseSnapshot(False, ("old", "part 1")),
            ResponseSnapshot(False, ("old", "part 2")),
            ResponseSnapshot(False, ("old", "part 2")),
        ]
    )

    result = _monitor(source).collect(("old",))

    assert result.completed is True
    assert result.response_text == "part 2"
    assert result.polls == 5


def test_compact_baseline_detects_new_message_without_storing_old_text() -> None:
    baseline = ResponseBaseline.from_messages(("old answer",))
    source = SequenceSource([ResponseSnapshot(False, ("old answer", "new answer"))])

    result = _monitor(source, stable=1).collect(baseline=baseline)

    assert baseline.message_count == 1
    assert baseline.latest_digest
    assert "old answer" not in str(baseline.to_dict())
    assert result.completed is True
    assert result.response_text == "new answer"


def test_unchanged_baseline_never_counts_as_new_response() -> None:
    source = SequenceSource([ResponseSnapshot(False, ("old",))])

    result = _monitor(source, timeout=2.0).collect(("old",))

    assert result.completed is False
    assert result.response_text == ""
    assert result.saw_activity is False
    assert "timed out" in result.reason


def test_timeout_after_partial_activity_is_not_completion() -> None:
    source = SequenceSource(
        [
            ResponseSnapshot(True, ("old", "partial")),
            ResponseSnapshot(True, ("old", "partial more")),
        ]
    )

    result = _monitor(source, timeout=2.0).collect(("old",))

    assert result.completed is False
    assert result.saw_activity is True
    assert result.response_text == "partial more"
    assert "timed out" in result.reason
