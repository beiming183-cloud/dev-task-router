from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .config import (
    load_models,
    load_repository_context,
    load_rolling_context,
    load_surfaces,
)
from .mode_switch import ModeSwitchBackend, ModeSwitchController, RequestedProfile, SwitchResult
from .models import ModelLevel, Plan, TaskSpec, TaskStatus
from .retry import level_for_attempt
from .rolling_context import ContextPackBuilder, TaskContextPack
from .router import RuleRouter, RoutingDecision
from .state import StateStore


@dataclass(frozen=True, slots=True)
class LocalExecutionEnvelope:
    task_id: str
    stage: str
    step: str
    difficulty: ModelLevel
    context_pack: TaskContextPack
    requested_profile: RequestedProfile | None
    deterministic: bool

    def prompt_text(self) -> str:
        if self.deterministic:
            return ""
        return self.context_pack.to_markdown()

    def to_dict(self) -> dict[str, Any]:
        profile = None
        if self.requested_profile is not None:
            profile = {
                "surface": self.requested_profile.surface,
                "level": self.requested_profile.level.value,
                "family": self.requested_profile.family,
                "effort": self.requested_profile.effort,
                "label": self.requested_profile.label,
            }
        return {
            "task_id": self.task_id,
            "stage": self.stage,
            "step": self.step,
            "difficulty": self.difficulty.value,
            "deterministic": self.deterministic,
            "requested_profile": profile,
            "context_pack": self.context_pack.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class LocalExecutionGate:
    envelope: LocalExecutionEnvelope
    switch_result: SwitchResult | None
    allowed_to_dispatch: bool
    blocker: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        switch_data = None
        if self.switch_result is not None:
            result = self.switch_result
            switch_data = {
                "requested": {
                    "surface": result.requested.surface,
                    "level": result.requested.level.value,
                    "family": result.requested.family,
                    "effort": result.requested.effort,
                    "label": result.requested.label,
                },
                "actual": {
                    "family": result.actual_family,
                    "effort": result.actual_effort,
                },
                "verified": result.verified,
                "backend": result.backend,
                "changed": result.changed,
                "message": result.message,
            }
        return {
            "task": self.envelope.to_dict(),
            "switch": switch_data,
            "allowed_to_dispatch": self.allowed_to_dispatch,
            "blocker": self.blocker,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ConversationDispatchResult:
    accepted: bool
    backend: str
    message: str
    response_text: str = ""


class ConversationBackend(Protocol):
    name: str

    def dispatch(self, envelope: LocalExecutionEnvelope) -> ConversationDispatchResult: ...


class DryRunConversationBackend:
    """Never touches ChatGPT. Used to prove the dispatch contract without pretending execution happened."""

    name = "dry-run"

    def dispatch(self, envelope: LocalExecutionEnvelope) -> ConversationDispatchResult:
        return ConversationDispatchResult(
            accepted=False,
            backend=self.name,
            message=(
                "dry-run only: the task was prepared but was not sent to the canonical conversation"
            ),
        )


@dataclass(frozen=True, slots=True)
class LocalDispatchOutcome:
    gate: LocalExecutionGate
    dispatch: ConversationDispatchResult | None

    @property
    def dispatched(self) -> bool:
        return bool(self.dispatch and self.dispatch.accepted)

    def to_dict(self) -> dict[str, Any]:
        dispatch_data = None
        if self.dispatch is not None:
            dispatch_data = {
                "accepted": self.dispatch.accepted,
                "backend": self.dispatch.backend,
                "message": self.dispatch.message,
                "response_text": self.dispatch.response_text,
            }
        return {
            "gate": self.gate.to_dict(),
            "dispatch": dispatch_data,
            "dispatched": self.dispatched,
        }


class LocalConversationOrchestrator:
    """Prepare and gate the next Task for the current canonical ChatGPT conversation.

    V0.8 deliberately separates preparation/gating from a real UI conversation driver.
    A task may only reach ConversationBackend after the requested non-NONE profile has
    been verified by ModeSwitchController. Preparing a task never increments attempts
    or mutates Task status, so UI/infrastructure failures cannot accidentally trigger
    difficulty escalation.
    """

    def __init__(
        self,
        root: Path,
        plan: Plan,
        store: StateStore,
        *,
        mode_backend: ModeSwitchBackend | None = None,
        conversation_backend: ConversationBackend | None = None,
        surface: str = "chat",
        context_builder: ContextPackBuilder | None = None,
    ):
        self.root = root
        self.plan = plan
        self.store = store
        self.repository = load_repository_context(root)
        self.rolling = load_rolling_context(root, project=plan.project)
        self.router = RuleRouter(load_models(root), repository_context=self.repository)
        self.surfaces = load_surfaces(root)
        self.mode_backend = mode_backend
        self.conversation_backend = conversation_backend or DryRunConversationBackend()
        self.surface = surface
        self.context_builder = context_builder or ContextPackBuilder()

    def next_task(self) -> TaskSpec | None:
        state = self.store.ensure_for_plan(self.plan)
        for task in self.plan.tasks:
            if state["tasks"][task.id]["status"] != TaskStatus.PASSED.value:
                return task
        return None

    def _route_for_next_attempt(self, task: TaskSpec) -> RoutingDecision:
        state = self.store.ensure_for_plan(self.plan)
        task_state = state["tasks"][task.id]
        base = self.router.route(task)
        next_attempt = int(task_state.get("attempts", 0)) + 1
        level = level_for_attempt(base.level, next_attempt, task.escalate_after)
        if level == base.level:
            return base
        return self.router.route(
            task,
            override_level=level,
            override_reason=(
                f"retry escalation preview attempt {next_attempt}: "
                f"{base.level.value}->{level.value}"
            ),
        )

    @staticmethod
    def _requested_route_dict(route: RoutingDecision) -> dict[str, Any]:
        return {
            "level": route.level.value,
            "provider": route.profile.provider,
            "model": route.profile.model,
            "executor": route.profile.executor,
            "reason": route.reason,
            "confidence": route.confidence,
            "traits": list(route.traits),
        }

    def prepare(self, task: TaskSpec | None = None) -> LocalExecutionEnvelope:
        task = task or self.next_task()
        if task is None:
            raise ValueError("workflow has no unresolved task")

        state = self.store.ensure_for_plan(self.plan)
        route = self._route_for_next_attempt(task)
        deterministic = route.level == ModelLevel.NONE
        requested_profile: RequestedProfile | None = None
        requested_route = self._requested_route_dict(route)

        if not deterministic:
            decision = self.surfaces.route(route.level, self.surface)
            if not decision.resolved or decision.model is None:
                raise ValueError(
                    f"surface route unresolved for {self.surface}/{route.level.value}; "
                    "configure a concrete route before local dispatch"
                )
            requested_profile = RequestedProfile.from_surface_decision(decision)
            requested_route.update(
                {
                    "surface": decision.surface,
                    "family": requested_profile.family,
                    "effort": requested_profile.effort,
                    "label": requested_profile.label,
                }
            )

        pack = self.context_builder.build(
            self.plan,
            state,
            task,
            self.rolling,
            repository=self.repository,
            requested_route=requested_route,
        )
        return LocalExecutionEnvelope(
            task_id=task.id,
            stage=task.stage_id,
            step=task.step_id,
            difficulty=route.level,
            context_pack=pack,
            requested_profile=requested_profile,
            deterministic=deterministic,
        )

    def gate(self, envelope: LocalExecutionEnvelope) -> LocalExecutionGate:
        if envelope.deterministic:
            return LocalExecutionGate(
                envelope=envelope,
                switch_result=None,
                allowed_to_dispatch=False,
                blocker="DETERMINISTIC",
                message=(
                    "NONE task does not belong in the ChatGPT conversation; run it through the deterministic executor"
                ),
            )

        if envelope.context_pack.stale_context:
            return LocalExecutionGate(
                envelope=envelope,
                switch_result=None,
                allowed_to_dispatch=False,
                blocker="STALE_CONTEXT",
                message="refresh commit-sensitive repository context before dispatch",
            )

        if envelope.requested_profile is None:
            return LocalExecutionGate(
                envelope=envelope,
                switch_result=None,
                allowed_to_dispatch=False,
                blocker="ROUTE_UNRESOLVED",
                message="no concrete requested profile is available",
            )

        if self.mode_backend is None:
            return LocalExecutionGate(
                envelope=envelope,
                switch_result=None,
                allowed_to_dispatch=False,
                blocker="MODE_SWITCH_UNAVAILABLE",
                message="no local mode-switch backend is configured",
            )

        controller = ModeSwitchController(self.surfaces, self.mode_backend)
        result = self.mode_backend.switch(envelope.requested_profile)
        if not result.verified:
            return LocalExecutionGate(
                envelope=envelope,
                switch_result=result,
                allowed_to_dispatch=False,
                blocker="MODE_SWITCH",
                message="requested profile was not verified; dispatch is blocked",
            )

        if (
            result.actual_family != envelope.requested_profile.family
            or result.actual_effort != envelope.requested_profile.effort
        ):
            return LocalExecutionGate(
                envelope=envelope,
                switch_result=result,
                allowed_to_dispatch=False,
                blocker="PROFILE_MISMATCH",
                message="verified UI state does not match the requested profile",
            )

        return LocalExecutionGate(
            envelope=envelope,
            switch_result=result,
            allowed_to_dispatch=True,
            blocker=None,
            message="context and actual profile verified; task may be dispatched",
        )

    def dispatch(self, task: TaskSpec | None = None) -> LocalDispatchOutcome:
        envelope = self.prepare(task)
        gate = self.gate(envelope)
        if not gate.allowed_to_dispatch:
            return LocalDispatchOutcome(gate=gate, dispatch=None)

        result = self.conversation_backend.dispatch(envelope)
        return LocalDispatchOutcome(gate=gate, dispatch=result)
