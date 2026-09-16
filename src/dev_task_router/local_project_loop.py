from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import load_rolling_context, save_rolling_context
from .deterministic_runner import DeterministicTaskRunner
from .e2e_calibration import EndToEndCalibrationRecorder
from .execution_evidence import ExecutionEvidenceLedger
from .handoff import HandoffWriter
from .local_review import IndependentLocalReviewer
from .local_session import LocalCycleResult, LocalTaskCycle
from .models import Plan, TaskSpec, TaskStatus, WorkflowStatus
from .state import StateStore, now_iso


@dataclass(frozen=True, slots=True)
class LocalProjectLoopResult:
    cycles: tuple[LocalCycleResult, ...]
    stop_reason: str
    workflow_status: str

    @property
    def last(self) -> LocalCycleResult | None:
        return self.cycles[-1] if self.cycles else None

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycles": [item.to_dict() for item in self.cycles],
            "cycle_count": len(self.cycles),
            "stop_reason": self.stop_reason,
            "workflow_status": self.workflow_status,
        }


class LocalProjectLoop:
    """Bounded project-level loop over model, deterministic and review execution.

    Only verified PASS facts are written into rolling context. The assistant response
    is never mined for durable decisions or constraints. CHECK_FAILED and a clean
    independent REVIEW_FAILED may continue to another implementation attempt because
    they are genuine execution evidence; infrastructure and ambiguous states stop.

    V1.0 additionally treats end-to-end profile calibration as non-authoritative
    metadata: after a real model Task reaches final PASS, complete durable execution
    evidence may enrich the live calibration registry, but failure to record that
    metadata never changes the already verified Task result.

    A verified generated debug Task may reopen its failed deterministic source for one
    ordinary NONE recheck. The source keeps its previous attempts/failure history; it
    is never promoted into the model Task that fixed it.
    """

    CONTINUE_STATUSES = {"PASSED", "CHECK_FAILED", "REVIEW_FAILED"}

    def __init__(
        self,
        root: Path,
        plan: Plan,
        store: StateStore,
        cycle: LocalTaskCycle,
        *,
        deterministic_runner: DeterministicTaskRunner | None = None,
        reviewer_runner: IndependentLocalReviewer | None = None,
        e2e_calibration: EndToEndCalibrationRecorder | None = None,
    ):
        self.root = root
        self.plan = plan
        self.store = store
        self.cycle = cycle
        self.deterministic_runner = deterministic_runner
        self.evidence = getattr(cycle, "evidence", None) or ExecutionEvidenceLedger(root)
        if reviewer_runner is None and hasattr(cycle, "orchestrator") and hasattr(cycle, "sessions"):
            reviewer_runner = IndependentLocalReviewer(
                root,
                plan,
                store,
                cycle.orchestrator.router,
                cycle.sessions,
                evidence=self.evidence,
            )
        self.reviewer_runner = reviewer_runner
        self.e2e_calibration = e2e_calibration or EndToEndCalibrationRecorder(
            root,
            evidence=self.evidence,
            sessions=getattr(cycle, "sessions", None),
        )
        self.handoff = HandoffWriter(root)

    def _task(self, task_id: str) -> TaskSpec | None:
        for task in self.plan.tasks:
            if task.id == task_id:
                return task
        return None

    def _task_title(self, task_id: str) -> str:
        task = self._task(task_id)
        return task.title if task is not None else task_id

    def _task_stage(self, task_id: str) -> str:
        task = self._task(task_id)
        return task.stage_id if task is not None else "default"

    def _record_verified_pass(self, result: LocalCycleResult) -> None:
        if result.status != "PASSED" or not result.task_id:
            return
        rolling = load_rolling_context(self.root, project=self.plan.project)
        title = self._task_title(result.task_id)
        if result.dispatch_id:
            dispatch = result.dispatch_id[:12]
            task_note = f"Verified PASS by Checker; dispatch={dispatch}."
        else:
            task_note = "Verified deterministic PASS by command/checker."
        stage_note = f"Verified PASS {result.task_id}: {title}."
        updated_at = now_iso()
        rolling = rolling.with_task_note(
            result.task_id,
            task_note,
            updated_at=updated_at,
        ).with_stage_note(
            self._task_stage(result.task_id),
            stage_note,
            updated_at=updated_at,
        )
        # Do not advance last_commit here. Local file changes may not yet have a fresh
        # repository evidence anchor; stale detection must remain conservative.
        save_rolling_context(self.root, rolling)
        self.handoff.write(self.plan, self.store.ensure_for_plan(self.plan))

    def _record_e2e_profile_calibration(self, result: LocalCycleResult) -> None:
        if result.status != "PASSED" or not result.task_id or not result.dispatch_id:
            return
        task = self._task(result.task_id)
        if task is None:
            return
        # Reviewer writes its own durable evidence after the wrapped model cycle has
        # already synced once. Re-sync before validating the final PASS so the evidence
        # ledger sees the latest session/workflow status as well.
        sync = getattr(self.cycle, "sync_dispatch", None)
        if callable(sync):
            try:
                sync(result.dispatch_id)
            except (OSError, RuntimeError, ValueError):
                return
        self.e2e_calibration.try_record(task, result.dispatch_id)

    def _reopen_debug_source_after_pass(self, result: LocalCycleResult) -> None:
        if result.status != "PASSED" or not result.task_id:
            return
        state = self.store.ensure_for_plan(self.plan)
        debug_state = state["tasks"].get(result.task_id)
        if not isinstance(debug_state, dict):
            return
        source_id = str(debug_state.get("generated_from_debug_source") or "").strip()
        if not source_id:
            return
        source_state = state["tasks"].get(source_id)
        if not isinstance(source_state, dict):
            return
        if source_state.get("debug_task_id") != result.task_id:
            return
        if not source_state.get("debug_task_required"):
            return
        if source_state.get("status") not in {TaskStatus.FAILED.value, TaskStatus.BLOCKED.value}:
            return

        preserved_attempts = int(source_state.get("attempts", 0))
        source_state["status"] = TaskStatus.PENDING.value
        source_state["last_error"] = None
        source_state["last_failure_type"] = None
        source_state["finished_at"] = None
        source_state["debug_task_required"] = False
        source_state["debug_task_recheck_pending"] = True
        source_state["debug_task_resolved_by"] = result.task_id
        source_state["debug_task_resolved_at"] = now_iso()
        state["status"] = WorkflowStatus.READY.value
        state["current_task"] = None
        self.store.save(state)
        self.evidence.record(
            task_id=source_id,
            dispatch_id=result.dispatch_id,
            kind="DEBUG_SOURCE_REOPENED",
            data={
                "debug_task_id": result.task_id,
                "preserved_attempts": preserved_attempts,
                "next_execution": "deterministic_recheck",
            },
        )
        self.handoff.write(self.plan, state)

    def run_one(self) -> LocalCycleResult:
        result = self.cycle.run_next()
        if result.status == "DETERMINISTIC" and self.deterministic_runner is not None:
            task = self.cycle.orchestrator.next_task()
            if task is None:
                result = LocalCycleResult("", "NO_TASK", None, False, "workflow has no unresolved task")
            else:
                deterministic = self.deterministic_runner.run(task)
                result = LocalCycleResult(
                    deterministic.task_id,
                    deterministic.status,
                    None,
                    False,
                    deterministic.message,
                    check=deterministic.check,
                )

        if (
            result.status == "REVIEW_REQUIRED"
            and self.reviewer_runner is not None
            and result.task_id
            and result.dispatch_id
        ):
            result = self.reviewer_runner.run(result.task_id, result.dispatch_id)

        self._record_verified_pass(result)
        self._record_e2e_profile_calibration(result)
        self._reopen_debug_source_after_pass(result)
        return result

    def run_until_blocked(self, *, max_cycles: int = 10) -> LocalProjectLoopResult:
        if max_cycles < 1:
            raise ValueError("max_cycles must be >= 1")

        results: list[LocalCycleResult] = []
        stop_reason = "MAX_CYCLES"
        for _ in range(max_cycles):
            result = self.run_one()
            results.append(result)

            if result.status == "NO_TASK":
                stop_reason = "COMPLETE"
                break
            if result.status not in self.CONTINUE_STATUSES:
                stop_reason = result.status
                break
        else:
            stop_reason = "MAX_CYCLES"

        state = self.store.ensure_for_plan(self.plan)
        return LocalProjectLoopResult(
            cycles=tuple(results),
            stop_reason=stop_reason,
            workflow_status=str(state.get("status", "UNKNOWN")),
        )
