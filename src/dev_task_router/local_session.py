from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .checker import CheckReport, TaskChecker, git_snapshot_digest
from .config import autodev_dir
from .conversation_ui import WindowsUIAConversationBackend
from .handoff import HandoffWriter
from .local_loop import LocalConversationOrchestrator, LocalExecutionEnvelope
from .models import ModelLevel, Plan, TaskSpec, TaskStatus, WorkflowStatus
from .response_monitor import (
    ConversationResponseMonitor,
    ResponseBaseline,
    ResponseCollectionResult,
)
from .state import StateStore, now_iso


_ACTIVE_SESSION_STATUSES = {
    "PREPARED",
    "SUBMITTED",
    "WAITING_RESPONSE",
    "COLLECTED",
    "CHECKED",
    "REVIEW_REQUIRED",
}


@dataclass(frozen=True, slots=True)
class LocalCycleResult:
    task_id: str
    status: str
    dispatch_id: str | None
    infrastructure_failure: bool
    message: str
    response: ResponseCollectionResult | None = None
    check: CheckReport | None = None

    @property
    def completed(self) -> bool:
        return self.status in {
            "PASSED",
            "CHECK_FAILED",
            "FAILED",
            "BLOCKED",
            "REVIEW_REQUIRED",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "dispatch_id": self.dispatch_id,
            "infrastructure_failure": self.infrastructure_failure,
            "message": self.message,
            "response": self.response.to_dict() if self.response else None,
            "check": (
                {
                    "ok": self.check.ok,
                    "message": self.check.message,
                    "evidence": self.check.evidence,
                    "returncode": self.check.returncode,
                    "failure_type": self.check.failure_type,
                }
                if self.check
                else None
            ),
        }


class LocalSessionStore:
    """Small recovery ledger for local same-conversation execution.

    It stores hashes/metadata plus response file paths, not conversation history.
    Assistant response bodies are written separately under `.autodev/local-responses/`.
    """

    def __init__(self, root: Path):
        self.root = root
        self.path = autodev_dir(root) / "local-sessions.json"
        self.response_dir = autodev_dir(root) / "local-responses"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "sessions": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("sessions"), dict):
            raise ValueError("local-sessions.json must contain a sessions mapping")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self, dispatch_id: str) -> dict[str, Any] | None:
        return self._load()["sessions"].get(dispatch_id)

    def active_for_task(self, task_id: str) -> tuple[str, dict[str, Any]] | None:
        sessions = self._load()["sessions"]
        candidates = [
            (dispatch_id, item)
            for dispatch_id, item in sessions.items()
            if item.get("task_id") == task_id and item.get("status") in _ACTIVE_SESSION_STATUSES
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda pair: str(pair[1].get("updated_at", "")), reverse=True)
        return candidates[0]

    def create(
        self,
        dispatch_id: str,
        envelope: LocalExecutionEnvelope,
        *,
        baseline: ResponseBaseline,
        before_git_digest: str | None,
    ) -> None:
        data = self._load()
        existing = data["sessions"].get(dispatch_id)
        if existing and existing.get("status") in _ACTIVE_SESSION_STATUSES:
            raise RuntimeError(f"local session already active: {dispatch_id}")
        profile = envelope.requested_profile
        data["sessions"][dispatch_id] = {
            "task_id": envelope.task_id,
            "status": "PREPARED",
            "difficulty": envelope.difficulty.value,
            "requested_profile": (
                {
                    "surface": profile.surface,
                    "family": profile.family,
                    "effort": profile.effort,
                    "label": profile.label,
                }
                if profile
                else None
            ),
            "baseline": baseline.to_dict(),
            "before_git_digest": before_git_digest,
            "response_path": None,
            "response_digest": None,
            "check": None,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        self._save(data)

    def update(self, dispatch_id: str, **changes: Any) -> dict[str, Any]:
        data = self._load()
        item = data["sessions"].get(dispatch_id)
        if item is None:
            raise RuntimeError(f"unknown local session: {dispatch_id}")
        item.update(changes)
        item["updated_at"] = now_iso()
        self._save(data)
        return item

    def save_response(self, dispatch_id: str, response_text: str) -> Path:
        self.response_dir.mkdir(parents=True, exist_ok=True)
        path = self.response_dir / f"{dispatch_id}.txt"
        path.write_text(response_text, encoding="utf-8")
        digest = hashlib.sha256(response_text.encode("utf-8")).hexdigest()
        relative = path.relative_to(self.root).as_posix()
        self.update(
            dispatch_id,
            status="COLLECTED",
            response_path=relative,
            response_digest=digest,
        )
        return path


class LocalTaskCycle:
    """Run one non-deterministic Task through the current canonical conversation.

    Infrastructure stages (gate, UI dispatch, response collection) never increment the
    model-attempt counter. The attempt is recorded only when a completed response is
    handed to Checker. This prevents UI/network timeouts from causing difficulty
    promotion while still letting real CHECK/DIFF failures drive the next route.
    """

    def __init__(
        self,
        root: Path,
        plan: Plan,
        store: StateStore,
        orchestrator: LocalConversationOrchestrator,
        monitor: ConversationResponseMonitor,
        *,
        checker: TaskChecker | None = None,
        sessions: LocalSessionStore | None = None,
    ):
        self.root = root
        self.plan = plan
        self.store = store
        self.orchestrator = orchestrator
        self.monitor = monitor
        self.checker = checker or TaskChecker()
        self.sessions = sessions or LocalSessionStore(root)
        self.handoff = HandoffWriter(root)

    def _task(self, task_id: str) -> TaskSpec:
        for task in self.plan.tasks:
            if task.id == task_id:
                return task
        raise ValueError(f"unknown task: {task_id}")

    @staticmethod
    def _dispatch_id(envelope: LocalExecutionEnvelope) -> str:
        return WindowsUIAConversationBackend.dispatch_id(envelope)

    def run_next(self) -> LocalCycleResult:
        task = self.orchestrator.next_task()
        if task is None:
            return LocalCycleResult("", "NO_TASK", None, False, "workflow has no unresolved task")

        active = self.sessions.active_for_task(task.id)
        if active is not None:
            dispatch_id, session = active
            if session.get("status") == "PREPARED":
                return LocalCycleResult(
                    task.id,
                    "RECOVERY_REQUIRED",
                    dispatch_id,
                    True,
                    "a PREPARED session has ambiguous send state; reconcile it before any resend",
                )
            return self._resume(task, dispatch_id, session)

        return self._dispatch_new(task)

    def _dispatch_new(self, task: TaskSpec) -> LocalCycleResult:
        try:
            envelope = self.orchestrator.prepare(task)
            gate = self.orchestrator.gate(envelope)
        except (RuntimeError, ValueError) as exc:
            return LocalCycleResult(task.id, "GATE_FAILED", None, True, str(exc))

        if envelope.deterministic:
            return LocalCycleResult(
                task.id,
                "DETERMINISTIC",
                None,
                False,
                "NONE task belongs to the deterministic executor, not the ChatGPT conversation",
            )
        if not gate.allowed_to_dispatch:
            return LocalCycleResult(
                task.id,
                gate.blocker or "GATE_FAILED",
                None,
                True,
                gate.message,
            )

        try:
            baseline_snapshot = self.monitor.source.snapshot()
        except (RuntimeError, ValueError) as exc:
            return LocalCycleResult(task.id, "RESPONSE_SOURCE", None, True, str(exc))
        baseline = ResponseBaseline.from_messages(baseline_snapshot.messages)

        before_digest = git_snapshot_digest(self.root) if task.require_diff else None
        if task.require_diff and before_digest is None:
            return LocalCycleResult(
                task.id,
                "GIT_SNAPSHOT",
                None,
                True,
                "require_diff needs a Git worktree before dispatch; nothing was sent",
            )

        dispatch_id = self._dispatch_id(envelope)
        try:
            self.sessions.create(
                dispatch_id,
                envelope,
                baseline=baseline,
                before_git_digest=before_digest,
            )
            dispatch = self.orchestrator.conversation_backend.dispatch(envelope)
        except (RuntimeError, ValueError) as exc:
            # PREPARED is deliberately left sticky. We cannot know whether a backend
            # raised before or after an ambiguous UI submit boundary.
            return LocalCycleResult(task.id, "DISPATCH_AMBIGUOUS", dispatch_id, True, str(exc))

        if not dispatch.accepted:
            self.sessions.update(dispatch_id, status="REJECTED", dispatch_message=dispatch.message)
            return LocalCycleResult(
                task.id,
                "DISPATCH_REJECTED",
                dispatch_id,
                True,
                dispatch.message,
            )

        session = self.sessions.update(
            dispatch_id,
            status="SUBMITTED",
            dispatch_backend=dispatch.backend,
            dispatch_message=dispatch.message,
        )
        return self._collect_and_check(task, dispatch_id, session)

    def _resume(
        self,
        task: TaskSpec,
        dispatch_id: str,
        session: dict[str, Any],
    ) -> LocalCycleResult:
        status = session.get("status")
        if status == "REVIEW_REQUIRED":
            return LocalCycleResult(
                task.id,
                "REVIEW_REQUIRED",
                dispatch_id,
                False,
                "checker already passed; independent review is still required before PASS",
            )
        if status == "CHECKED":
            raw = session.get("check") or {}
            check = CheckReport(
                ok=bool(raw.get("ok")),
                message=str(raw.get("message", "checker result recovered")),
                evidence="",
                returncode=raw.get("returncode"),
                failure_type=raw.get("failure_type"),
            )
            route = self._route_from_session(task, session)
            return self._record_check(task, route, dispatch_id, check)
        if status == "COLLECTED":
            return self._check_collected(task, dispatch_id, session)
        return self._collect_and_check(task, dispatch_id, session)

    def _collect_and_check(
        self,
        task: TaskSpec,
        dispatch_id: str,
        session: dict[str, Any],
    ) -> LocalCycleResult:
        baseline = ResponseBaseline.from_dict(session.get("baseline") or {})
        try:
            response = self.monitor.collect(baseline=baseline)
        except (RuntimeError, ValueError) as exc:
            self.sessions.update(
                dispatch_id,
                status="WAITING_RESPONSE",
                response_error=str(exc),
            )
            return LocalCycleResult(
                task.id,
                "WAITING_RESPONSE",
                dispatch_id,
                True,
                str(exc),
            )

        if not response.completed:
            self.sessions.update(
                dispatch_id,
                status="WAITING_RESPONSE",
                response_error=response.reason,
            )
            return LocalCycleResult(
                task.id,
                "WAITING_RESPONSE",
                dispatch_id,
                True,
                response.reason,
                response=response,
            )

        self.sessions.save_response(dispatch_id, response.response_text)
        session = self.sessions.get(dispatch_id) or session
        result = self._check_collected(task, dispatch_id, session)
        return LocalCycleResult(
            result.task_id,
            result.status,
            result.dispatch_id,
            result.infrastructure_failure,
            result.message,
            response=response,
            check=result.check,
        )

    def _route_from_session(self, task: TaskSpec, session: dict[str, Any]):
        level = ModelLevel(str(session.get("difficulty", "")).upper())
        return self.orchestrator.router.route(
            task,
            override_level=level,
            override_reason="recorded local conversation dispatch route",
        )

    def _check_collected(
        self,
        task: TaskSpec,
        dispatch_id: str,
        session: dict[str, Any],
    ) -> LocalCycleResult:
        route = self._route_from_session(task, session)
        check = self.checker.run(
            task,
            root=self.root,
            route=route,
            before_git_digest=session.get("before_git_digest"),
        )
        self.sessions.update(
            dispatch_id,
            status="CHECKED",
            check={
                "ok": check.ok,
                "message": check.message,
                "failure_type": check.failure_type,
                "returncode": check.returncode,
            },
        )
        return self._record_check(task, route, dispatch_id, check)

    def _record_check(self, task: TaskSpec, route, dispatch_id: str, check: CheckReport) -> LocalCycleResult:
        state = self.store.ensure_for_plan(self.plan)
        task_state = state["tasks"][task.id]

        # Idempotent crash recovery: once this dispatch_id reached durable workflow
        # state, replaying CHECKED must not increment attempts or append failures again.
        if task_state.get("local_dispatch_id") == dispatch_id:
            current = task_state.get("status")
            if current == TaskStatus.PASSED.value:
                self.sessions.update(dispatch_id, status="PASSED")
                return LocalCycleResult(task.id, "PASSED", dispatch_id, False, "check result already recorded", check=check)
            if current == TaskStatus.RUNNING.value and task.review:
                self.sessions.update(dispatch_id, status="REVIEW_REQUIRED")
                return LocalCycleResult(task.id, "REVIEW_REQUIRED", dispatch_id, False, "review requirement already recorded", check=check)
            if current == TaskStatus.BLOCKED.value:
                self.sessions.update(dispatch_id, status="BLOCKED")
                return LocalCycleResult(task.id, "BLOCKED", dispatch_id, False, task_state.get("last_error") or check.message, check=check)
            if current == TaskStatus.FAILED.value:
                terminal = int(task_state.get("attempts", 0)) >= task.max_attempts
                session_status = "FAILED" if terminal else "CHECK_FAILED"
                self.sessions.update(dispatch_id, status=session_status)
                return LocalCycleResult(task.id, session_status, dispatch_id, False, task_state.get("last_error") or check.message, check=check)

        task_state["attempts"] = int(task_state.get("attempts", 0)) + 1
        task_state["started_at"] = task_state.get("started_at") or now_iso()
        task_state["finished_at"] = now_iso()
        route_data = {
            "level": route.level.value,
            "provider": route.profile.provider,
            "model": route.profile.model,
            "executor": route.profile.executor,
            "reason": route.reason,
            "confidence": route.confidence,
            "traits": list(route.traits),
        }
        task_state["route"] = route_data
        task_state.setdefault("route_history", []).append(
            {"attempt": task_state["attempts"], **route_data}
        )
        task_state["local_dispatch_id"] = dispatch_id

        if check.ok:
            task_state["last_error"] = None
            task_state["last_failure_type"] = None
            if task.review:
                task_state["status"] = TaskStatus.RUNNING.value
                state["status"] = WorkflowStatus.RUNNING.value
                state["current_task"] = task.id
                self.store.save(state)
                self.handoff.write(self.plan, state)
                self.sessions.update(dispatch_id, status="REVIEW_REQUIRED")
                return LocalCycleResult(
                    task.id,
                    "REVIEW_REQUIRED",
                    dispatch_id,
                    False,
                    "checker passed; independent review is still required before PASS",
                    check=check,
                )

            task_state["status"] = TaskStatus.PASSED.value
            state["current_task"] = None
            all_passed = all(
                state["tasks"][item.id]["status"] == TaskStatus.PASSED.value
                for item in self.plan.tasks
            )
            state["status"] = (
                WorkflowStatus.PASSED.value if all_passed else WorkflowStatus.READY.value
            )
            self.store.save(state)
            self.handoff.write(self.plan, state)
            self.sessions.update(dispatch_id, status="PASSED")
            return LocalCycleResult(
                task.id,
                "PASSED",
                dispatch_id,
                False,
                "response collected and checker passed",
                check=check,
            )

        failure_type = check.failure_type or "CHECK"
        task_state["status"] = TaskStatus.FAILED.value
        task_state["last_error"] = check.message
        task_state["last_failure_type"] = failure_type
        task_state.setdefault("failures", []).append(
            {
                "attempt": task_state["attempts"],
                "type": failure_type,
                "message": check.message,
                "route": route_data,
                "dispatch_id": dispatch_id,
                "at": now_iso(),
            }
        )
        exhausted = task_state["attempts"] >= task.max_attempts
        if exhausted:
            terminal = TaskStatus.BLOCKED.value if task.max_attempts > 1 else TaskStatus.FAILED.value
            task_state["status"] = terminal
            state["status"] = (
                WorkflowStatus.BLOCKED.value
                if task.max_attempts > 1
                else WorkflowStatus.FAILED.value
            )
            state["current_task"] = task.id
            session_status = "BLOCKED" if task.max_attempts > 1 else "FAILED"
        else:
            state["status"] = WorkflowStatus.READY.value
            state["current_task"] = None
            session_status = "CHECK_FAILED"

        self.store.save(state)
        self.handoff.write(self.plan, state)
        self.sessions.update(dispatch_id, status=session_status)
        return LocalCycleResult(
            task.id,
            session_status,
            dispatch_id,
            False,
            check.message,
            check=check,
        )
