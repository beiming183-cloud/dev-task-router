from __future__ import annotations

from dataclasses import dataclass

from dev_task_router.checker import CheckReport
from dev_task_router.config import write_default_files
from dev_task_router.local_loop import (
    ConversationDispatchResult,
    LocalConversationOrchestrator,
)
from dev_task_router.local_session import LocalSessionStore, LocalTaskCycle
from dev_task_router.mode_switch import RequestedProfile, SwitchResult
from dev_task_router.models import ModelLevel, Plan
from dev_task_router.response_monitor import ConversationResponseMonitor, ResponseSnapshot
from dev_task_router.state import StateStore


def _plan(*, review: bool = False, max_attempts: int = 3) -> Plan:
    return Plan.from_dict(
        {
            "version": 3,
            "project": "demo",
            "stages": [
                {
                    "id": "stage",
                    "steps": [
                        {
                            "id": "step",
                            "tasks": [
                                {
                                    "id": "task",
                                    "title": "Implement bounded feature",
                                    "kind": "normal_code",
                                    "prompt": "Implement the next bounded feature and keep behavior compatible.",
                                    "acceptance": ["targeted verification passes"],
                                    "max_attempts": max_attempts,
                                    "escalate_after": 1,
                                    "review": review,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def _root(tmp_path, plan: Plan) -> StateStore:
    write_default_files(tmp_path, plan.project)
    store = StateStore(tmp_path)
    store.create(plan)
    return store


@dataclass
class VerifiedSwitchBackend:
    name: str = "fake-verified"

    def probe(self):
        return []

    def switch(self, requested: RequestedProfile) -> SwitchResult:
        return SwitchResult(
            requested=requested,
            actual_family=requested.family,
            actual_effort=requested.effort,
            verified=True,
            backend=self.name,
            changed=True,
            message="verified",
        )


@dataclass
class RecordingConversation:
    name: str = "fake-conversation"
    calls: int = 0
    efforts: list[str | None] | None = None

    def __post_init__(self) -> None:
        if self.efforts is None:
            self.efforts = []

    def dispatch(self, envelope):
        self.calls += 1
        self.efforts.append(envelope.requested_profile.effort)
        return ConversationDispatchResult(
            accepted=True,
            backend=self.name,
            message="accepted",
        )


class QueueSource:
    def __init__(self, snapshots: list[ResponseSnapshot]):
        self.snapshots = snapshots
        self.index = 0

    def reset(self, snapshots: list[ResponseSnapshot]) -> None:
        self.snapshots = snapshots
        self.index = 0

    def snapshot(self) -> ResponseSnapshot:
        if not self.snapshots:
            raise RuntimeError("no response snapshots configured")
        if self.index >= len(self.snapshots):
            return self.snapshots[-1]
        item = self.snapshots[self.index]
        self.index += 1
        return item


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def now(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


def _monitor(source: QueueSource, *, timeout: float = 10.0) -> ConversationResponseMonitor:
    clock = FakeClock()
    return ConversationResponseMonitor(
        source,
        poll_interval_seconds=1.0,
        timeout_seconds=timeout,
        stable_polls=2,
        clock=clock.now,
        sleeper=clock.sleep,
    )


def _cycle(tmp_path, plan: Plan, store: StateStore, source: QueueSource, conversation, *, checker=None, timeout=10.0):
    orchestrator = LocalConversationOrchestrator(
        tmp_path,
        plan,
        store,
        mode_backend=VerifiedSwitchBackend(),
        conversation_backend=conversation,
    )
    return LocalTaskCycle(
        tmp_path,
        plan,
        store,
        orchestrator,
        _monitor(source, timeout=timeout),
        checker=checker,
    )


def test_full_local_cycle_requires_response_and_checker_before_pass(tmp_path) -> None:
    plan = _plan()
    store = _root(tmp_path, plan)
    conversation = RecordingConversation()
    source = QueueSource(
        [
            ResponseSnapshot(False, ("old",)),  # pre-send baseline
            ResponseSnapshot(True, ("old", "working")),
            ResponseSnapshot(False, ("old", "done")),
            ResponseSnapshot(False, ("old", "done")),
            ResponseSnapshot(False, ("old", "done")),
        ]
    )

    result = _cycle(tmp_path, plan, store, source, conversation).run_next()
    state = store.load()

    assert result.status == "PASSED"
    assert result.response is not None and result.response.completed is True
    assert result.check is not None and result.check.ok is True
    assert conversation.calls == 1
    assert state["tasks"]["task"]["attempts"] == 1
    assert state["tasks"]["task"]["status"] == "PASSED"
    session = LocalSessionStore(tmp_path).get(result.dispatch_id)
    assert session["status"] == "PASSED"
    assert session["response_digest"]
    assert (tmp_path / session["response_path"]).read_text(encoding="utf-8") == "done"


def test_response_timeout_resumes_same_dispatch_without_consuming_attempt_or_resending(tmp_path) -> None:
    plan = _plan()
    store = _root(tmp_path, plan)
    conversation = RecordingConversation()
    source = QueueSource(
        [
            ResponseSnapshot(False, ("old",)),  # baseline
            ResponseSnapshot(True, ("old", "partial")),
        ]
    )
    cycle = _cycle(tmp_path, plan, store, source, conversation, timeout=2.0)

    first = cycle.run_next()
    first_state = store.load()

    assert first.status == "WAITING_RESPONSE"
    assert first.infrastructure_failure is True
    assert conversation.calls == 1
    assert first_state["tasks"]["task"]["attempts"] == 0
    assert first_state["tasks"]["task"]["status"] == "PENDING"

    source.reset(
        [
            ResponseSnapshot(False, ("old", "done")),
            ResponseSnapshot(False, ("old", "done")),
            ResponseSnapshot(False, ("old", "done")),
        ]
    )
    second = cycle.run_next()
    second_state = store.load()

    assert second.status == "PASSED"
    assert second.dispatch_id == first.dispatch_id
    assert conversation.calls == 1
    assert second_state["tasks"]["task"]["attempts"] == 1


class AlwaysFailChecker:
    def __init__(self) -> None:
        self.levels: list[ModelLevel] = []

    def run(self, task, *, root, route, before_git=None, before_git_digest=None):
        self.levels.append(route.level)
        return CheckReport(False, "verification failed", failure_type="CHECK", returncode=1)


def test_checker_failure_consumes_attempt_and_promotes_next_real_model_run(tmp_path) -> None:
    plan = _plan(max_attempts=3)
    store = _root(tmp_path, plan)
    conversation = RecordingConversation()
    checker = AlwaysFailChecker()
    source = QueueSource(
        [
            ResponseSnapshot(False, ("old",)),
            ResponseSnapshot(False, ("old", "done 1")),
            ResponseSnapshot(False, ("old", "done 1")),
            ResponseSnapshot(False, ("old", "done 1")),
            ResponseSnapshot(False, ("old", "done 1")),  # next baseline
            ResponseSnapshot(False, ("old", "done 1", "done 2")),
            ResponseSnapshot(False, ("old", "done 1", "done 2")),
            ResponseSnapshot(False, ("old", "done 1", "done 2")),
        ]
    )
    cycle = _cycle(tmp_path, plan, store, source, conversation, checker=checker)

    first = cycle.run_next()
    second = cycle.run_next()
    state = store.load()

    assert first.status == "CHECK_FAILED"
    assert second.status == "CHECK_FAILED"
    assert checker.levels == [ModelLevel.MEDIUM, ModelLevel.HIGH]
    assert conversation.efforts == ["medium", "high"]
    assert conversation.calls == 2
    assert state["tasks"]["task"]["attempts"] == 2
    assert len(state["tasks"]["task"]["failures"]) == 2


def test_review_required_is_sticky_and_does_not_dispatch_again(tmp_path) -> None:
    plan = _plan(review=True)
    store = _root(tmp_path, plan)
    conversation = RecordingConversation()
    source = QueueSource(
        [
            ResponseSnapshot(False, ("old",)),
            ResponseSnapshot(False, ("old", "done")),
            ResponseSnapshot(False, ("old", "done")),
            ResponseSnapshot(False, ("old", "done")),
        ]
    )
    cycle = _cycle(tmp_path, plan, store, source, conversation)

    first = cycle.run_next()
    second = cycle.run_next()

    assert first.status == "REVIEW_REQUIRED"
    assert second.status == "REVIEW_REQUIRED"
    assert conversation.calls == 1
    assert store.load()["tasks"]["task"]["attempts"] == 1
