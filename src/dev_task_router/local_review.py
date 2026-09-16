from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .config import autodev_dir
from .execution_evidence import ExecutionEvidenceLedger
from .executor import ExecutorRegistry
from .handoff import HandoffWriter
from .local_session import LocalCycleResult, LocalSessionStore
from .models import Plan, TaskSpec, TaskStatus, WorkflowStatus
from .reviewer import Reviewer
from .router import RuleRouter
from .state import StateStore, now_iso


LOCAL_REVIEW_FILE = "local-review.yaml"


@dataclass(frozen=True, slots=True)
class LocalReviewerConfig:
    enabled: bool = False
    allowed_executors: tuple[str, ...] = ("agent-cli",)
    allowed_providers: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocalReviewerConfig":
        if not isinstance(data, dict):
            raise ValueError("local reviewer config must be a mapping")

        def strings(value: Any, name: str, default: tuple[str, ...]) -> tuple[str, ...]:
            if value is None:
                return default
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"local reviewer {name} must be a string list")
            return tuple(item.strip() for item in value if item.strip())

        return cls(
            enabled=bool(data.get("enabled", False)),
            allowed_executors=strings(
                data.get("allowed_executors"),
                "allowed_executors",
                ("agent-cli",),
            ),
            allowed_providers=strings(
                data.get("allowed_providers"),
                "allowed_providers",
                (),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "enabled": self.enabled,
            "allowed_executors": list(self.allowed_executors),
            "allowed_providers": list(self.allowed_providers),
        }


def load_local_reviewer_config(root: Path) -> LocalReviewerConfig:
    path = autodev_dir(root) / LOCAL_REVIEW_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(LocalReviewerConfig().to_dict(), sort_keys=False),
            encoding="utf-8",
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{LOCAL_REVIEW_FILE} must contain a YAML mapping")
    return LocalReviewerConfig.from_dict(data)


class IndependentLocalReviewer:
    """Run review only through an explicitly configured external executor.

    The canonical ChatGPT conversation is intentionally not accepted as an
    independent reviewer. Review infrastructure failures keep REVIEW_REQUIRED sticky
    and do not increment the implementation attempt counter.
    """

    def __init__(
        self,
        root: Path,
        plan: Plan,
        store: StateStore,
        router: RuleRouter,
        sessions: LocalSessionStore,
        *,
        config: LocalReviewerConfig | None = None,
        registry: ExecutorRegistry | None = None,
        evidence: ExecutionEvidenceLedger | None = None,
    ):
        self.root = root
        self.plan = plan
        self.store = store
        self.router = router
        self.sessions = sessions
        self.config = config or load_local_reviewer_config(root)
        self.registry = registry or ExecutorRegistry()
        self.reviewer = Reviewer(router, self.registry)
        self.evidence = evidence or ExecutionEvidenceLedger(root)
        self.handoff = HandoffWriter(root)

    def _task(self, task_id: str) -> TaskSpec:
        for task in self.plan.tasks:
            if task.id == task_id:
                return task
        raise ValueError(f"unknown task: {task_id}")

    def _gate(self, task: TaskSpec):
        if not task.review:
            return None, "task does not request independent review"
        if not self.config.enabled:
            return None, f"independent reviewer is disabled in {LOCAL_REVIEW_FILE}"
        route = self.router.decision_for_level(task.review_level, "independent local reviewer")
        profile = route.profile
        if profile.executor not in self.config.allowed_executors:
            return None, (
                f"review executor {profile.executor!r} is not in the explicitly allowed independent executor set"
            )
        if self.config.allowed_providers and profile.provider not in self.config.allowed_providers:
            return None, (
                f"review provider {profile.provider!r} is not in the explicitly allowed independent provider set"
            )
        if not profile.command:
            return None, "independent reviewer profile requires an external command template"
        return route, None

    @staticmethod
    def _review_digest(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest() if raw else ""

    def run(self, task_id: str, dispatch_id: str) -> LocalCycleResult:
        task = self._task(task_id)
        state = self.store.ensure_for_plan(self.plan)
        item = state["tasks"][task.id]
        session = self.sessions.get(dispatch_id)
        if not isinstance(session, dict) or session.get("task_id") != task.id:
            return LocalCycleResult(
                task.id,
                "REVIEW_REQUIRED",
                dispatch_id,
                True,
                "independent review cannot start because the REVIEW_REQUIRED session is missing",
            )
        if session.get("status") != "REVIEW_REQUIRED":
            return LocalCycleResult(
                task.id,
                "REVIEW_REQUIRED",
                dispatch_id,
                True,
                f"independent review requires REVIEW_REQUIRED session, got {session.get('status')!r}",
            )
        if item.get("status") != TaskStatus.RUNNING.value:
            return LocalCycleResult(
                task.id,
                "REVIEW_REQUIRED",
                dispatch_id,
                True,
                "independent review requires the workflow task to remain RUNNING after Checker PASS",
            )

        route, blocker = self._gate(task)
        if route is None:
            return LocalCycleResult(
                task.id,
                "REVIEW_REQUIRED",
                dispatch_id,
                True,
                blocker or "independent reviewer is unavailable",
            )

        profile = route.profile
        self.evidence.record(
            task_id=task.id,
            dispatch_id=dispatch_id,
            kind="REVIEW_STARTED",
            data={
                "level": task.review_level.value,
                "provider": profile.provider,
                "model": profile.model,
                "executor": profile.executor,
            },
        )

        raw_check = session.get("check") if isinstance(session.get("check"), dict) else {}
        checker_evidence = str(raw_check.get("message") or "checks passed")
        response_digest = str(session.get("response_digest") or "")
        if response_digest:
            checker_evidence += f"\nresponse_digest: {response_digest}"

        report = self.reviewer.review(
            task,
            root=self.root,
            checker_evidence=checker_evidence,
        )
        review_digest = self._review_digest(report.raw)
        explicit_fail = bool(
            report.returncode == 0 and report.message.strip().upper().startswith("FAIL")
        )
        verdict = "PASS" if report.ok else ("FAIL" if explicit_fail else "ERROR")
        self.evidence.record(
            task_id=task.id,
            dispatch_id=dispatch_id,
            kind="REVIEWED",
            data={
                "verdict": verdict,
                "ok": report.ok,
                "message": report.message,
                "returncode": report.returncode,
                "review_digest": review_digest,
            },
        )

        state = self.store.load()
        item = state["tasks"][task.id]
        item["review"] = {
            "ok": report.ok,
            "message": report.message,
            "level": task.review_level.value,
            "provider": profile.provider,
            "model": profile.model,
            "executor": profile.executor,
            "digest": review_digest,
        }

        if not report.ok and not explicit_fail:
            # Reviewer process/protocol failure is infrastructure, not evidence that
            # the implementation itself failed. Keep the task/session reviewable.
            self.store.save(state)
            self.handoff.write(self.plan, state)
            return LocalCycleResult(
                task.id,
                "REVIEW_INFRASTRUCTURE",
                dispatch_id,
                True,
                report.message,
            )

        if report.ok:
            item["status"] = TaskStatus.PASSED.value
            item["finished_at"] = now_iso()
            item["last_error"] = None
            item["last_failure_type"] = None
            state["current_task"] = None
            all_passed = all(
                state["tasks"][candidate.id]["status"] == TaskStatus.PASSED.value
                for candidate in self.plan.tasks
            )
            state["status"] = (
                WorkflowStatus.PASSED.value if all_passed else WorkflowStatus.READY.value
            )
            self.store.save(state)
            self.sessions.update(
                dispatch_id,
                status="PASSED",
                review=item["review"],
            )
            self.handoff.write(self.plan, state)
            self.evidence.record(
                task_id=task.id,
                dispatch_id=dispatch_id,
                kind="STATE_RECORDED",
                data={
                    "task_status": item["status"],
                    "attempts": item.get("attempts"),
                    "last_failure_type": None,
                    "workflow_status": state["status"],
                    "reviewed": True,
                },
            )
            return LocalCycleResult(
                task.id,
                "PASSED",
                dispatch_id,
                False,
                "checker and independent reviewer passed",
            )

        # A clean FAIL verdict is genuine implementation evidence belonging to the
        # current implementation attempt. Do not increment attempts a second time.
        item["status"] = TaskStatus.FAILED.value
        item["finished_at"] = now_iso()
        item["last_error"] = report.message
        item["last_failure_type"] = "REVIEW"
        item.setdefault("failures", []).append(
            {
                "attempt": item.get("attempts", 0),
                "type": "REVIEW",
                "message": report.message,
                "route": item.get("route"),
                "dispatch_id": dispatch_id,
                "at": now_iso(),
            }
        )
        exhausted = int(item.get("attempts", 0)) >= task.max_attempts
        if exhausted:
            terminal = TaskStatus.BLOCKED.value if task.max_attempts > 1 else TaskStatus.FAILED.value
            item["status"] = terminal
            state["status"] = (
                WorkflowStatus.BLOCKED.value
                if task.max_attempts > 1
                else WorkflowStatus.FAILED.value
            )
            state["current_task"] = task.id
            result_status = "BLOCKED" if task.max_attempts > 1 else "FAILED"
        else:
            state["status"] = WorkflowStatus.READY.value
            state["current_task"] = None
            result_status = "REVIEW_FAILED"

        self.store.save(state)
        self.sessions.update(
            dispatch_id,
            status=result_status,
            review=item["review"],
        )
        self.handoff.write(self.plan, state)
        self.evidence.record(
            task_id=task.id,
            dispatch_id=dispatch_id,
            kind="STATE_RECORDED",
            data={
                "task_status": item["status"],
                "attempts": item.get("attempts"),
                "last_failure_type": "REVIEW",
                "workflow_status": state["status"],
                "reviewed": True,
            },
        )
        return LocalCycleResult(
            task.id,
            result_status,
            dispatch_id,
            False,
            report.message,
        )
