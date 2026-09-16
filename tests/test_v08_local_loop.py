from __future__ import annotations

from dataclasses import dataclass

from dev_task_router.config import save_repository_context, save_rolling_context, write_default_files
from dev_task_router.local_loop import (
    ConversationDispatchResult,
    LocalConversationOrchestrator,
)
from dev_task_router.mode_switch import RequestedProfile, SwitchResult
from dev_task_router.models import ModelLevel, Plan
from dev_task_router.repo_context import RepositoryContext
from dev_task_router.rolling_context import RollingProjectContext
from dev_task_router.state import StateStore


def _plan(kind: str = "complex_code") -> Plan:
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
                                    "title": "Do the next task",
                                    "kind": kind,
                                    "prompt": "Implement the next bounded change.",
                                    "acceptance": ["targeted tests pass"],
                                    "max_attempts": 3,
                                    "escalate_after": 1,
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def _root(tmp_path, plan: Plan):
    write_default_files(tmp_path, plan.project)
    store = StateStore(tmp_path)
    store.create(plan)
    save_rolling_context(
        tmp_path,
        RollingProjectContext.from_dict(
            {
                "project": plan.project,
                "goal": "Keep one canonical conversation while completing the project.",
                "constraints": ["Do not break existing behavior"],
            }
        ),
    )
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
            message="verified in test",
        )


@dataclass
class UnverifiedSwitchBackend:
    name: str = "fake-unverified"

    def probe(self):
        return []

    def switch(self, requested: RequestedProfile) -> SwitchResult:
        return SwitchResult(
            requested=requested,
            actual_family=None,
            actual_effort=None,
            verified=False,
            backend=self.name,
            changed=True,
            message="not verified",
        )


@dataclass
class MismatchSwitchBackend:
    name: str = "fake-mismatch"

    def probe(self):
        return []

    def switch(self, requested: RequestedProfile) -> SwitchResult:
        return SwitchResult(
            requested=requested,
            actual_family=requested.family,
            actual_effort="low" if requested.effort != "low" else "high",
            verified=True,
            backend=self.name,
            changed=True,
            message="wrong effort",
        )


@dataclass
class RecordingConversationBackend:
    name: str = "fake-conversation"
    calls: int = 0

    def dispatch(self, envelope):
        self.calls += 1
        assert envelope.context_pack.constraints == ("Do not break existing behavior",)
        return ConversationDispatchResult(
            accepted=True,
            backend=self.name,
            message="accepted",
            response_text="placeholder model response",
        )


def test_prepare_builds_context_and_requested_profile_without_mutating_attempts(tmp_path) -> None:
    plan = _plan("complex_code")
    store = _root(tmp_path, plan)
    orchestrator = LocalConversationOrchestrator(tmp_path, plan, store)

    envelope = orchestrator.prepare()
    state = store.load()

    assert envelope.task_id == "task"
    assert envelope.difficulty == ModelLevel.HIGH
    assert envelope.requested_profile is not None
    assert envelope.requested_profile.family == "sol"
    assert envelope.requested_profile.effort == "high"
    assert envelope.context_pack.constraints == ("Do not break existing behavior",)
    assert state["tasks"]["task"]["attempts"] == 0
    assert state["tasks"]["task"]["status"] == "PENDING"


def test_missing_mode_backend_blocks_dispatch_without_consuming_retry(tmp_path) -> None:
    plan = _plan("normal_code")
    store = _root(tmp_path, plan)
    orchestrator = LocalConversationOrchestrator(tmp_path, plan, store)

    outcome = orchestrator.dispatch()

    assert outcome.dispatched is False
    assert outcome.gate.blocker == "MODE_SWITCH_UNAVAILABLE"
    assert store.load()["tasks"]["task"]["attempts"] == 0


def test_unverified_mode_switch_blocks_dispatch(tmp_path) -> None:
    plan = _plan("normal_code")
    store = _root(tmp_path, plan)
    conversation = RecordingConversationBackend()
    orchestrator = LocalConversationOrchestrator(
        tmp_path,
        plan,
        store,
        mode_backend=UnverifiedSwitchBackend(),
        conversation_backend=conversation,
    )

    outcome = orchestrator.dispatch()

    assert outcome.gate.blocker == "MODE_SWITCH"
    assert outcome.gate.allowed_to_dispatch is False
    assert conversation.calls == 0
    assert store.load()["tasks"]["task"]["attempts"] == 0


def test_profile_mismatch_blocks_dispatch_even_when_backend_claims_verified(tmp_path) -> None:
    plan = _plan("normal_code")
    store = _root(tmp_path, plan)
    conversation = RecordingConversationBackend()
    orchestrator = LocalConversationOrchestrator(
        tmp_path,
        plan,
        store,
        mode_backend=MismatchSwitchBackend(),
        conversation_backend=conversation,
    )

    outcome = orchestrator.dispatch()

    assert outcome.gate.blocker == "PROFILE_MISMATCH"
    assert conversation.calls == 0


def test_stale_context_blocks_before_mode_switch(tmp_path) -> None:
    plan = _plan("normal_code")
    store = _root(tmp_path, plan)
    save_rolling_context(
        tmp_path,
        RollingProjectContext.from_dict(
            {
                "project": "demo",
                "constraints": ["Do not break existing behavior"],
                "last_commit": "old",
            }
        ),
    )
    save_repository_context(
        tmp_path,
        RepositoryContext(repository="owner/repo", branch="main", commit="new"),
    )
    conversation = RecordingConversationBackend()
    orchestrator = LocalConversationOrchestrator(
        tmp_path,
        plan,
        store,
        mode_backend=VerifiedSwitchBackend(),
        conversation_backend=conversation,
    )

    outcome = orchestrator.dispatch()

    assert outcome.gate.blocker == "STALE_CONTEXT"
    assert outcome.gate.switch_result is None
    assert conversation.calls == 0


def test_verified_profile_opens_dispatch_gate_but_does_not_mark_task_passed(tmp_path) -> None:
    plan = _plan("normal_code")
    store = _root(tmp_path, plan)
    conversation = RecordingConversationBackend()
    orchestrator = LocalConversationOrchestrator(
        tmp_path,
        plan,
        store,
        mode_backend=VerifiedSwitchBackend(),
        conversation_backend=conversation,
    )

    outcome = orchestrator.dispatch()
    state = store.load()

    assert outcome.gate.allowed_to_dispatch is True
    assert outcome.gate.blocker is None
    assert outcome.dispatched is True
    assert conversation.calls == 1
    # Dispatch acceptance is not task-completion evidence. Checker/workflow owns completion.
    assert state["tasks"]["task"]["status"] == "PENDING"
    assert state["tasks"]["task"]["attempts"] == 0


def test_none_task_is_kept_out_of_chat_conversation(tmp_path) -> None:
    plan = _plan("test")
    store = _root(tmp_path, plan)
    conversation = RecordingConversationBackend()
    orchestrator = LocalConversationOrchestrator(
        tmp_path,
        plan,
        store,
        mode_backend=VerifiedSwitchBackend(),
        conversation_backend=conversation,
    )

    outcome = orchestrator.dispatch()

    assert outcome.gate.envelope.deterministic is True
    assert outcome.gate.envelope.requested_profile is None
    assert outcome.gate.blocker == "DETERMINISTIC"
    assert conversation.calls == 0
