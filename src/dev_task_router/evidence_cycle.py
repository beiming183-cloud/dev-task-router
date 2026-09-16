from __future__ import annotations

from pathlib import Path
from typing import Any

from .checker import git_snapshot_digest
from .conversation_ui import DispatchLedger
from .execution_evidence import ExecutionEvidenceLedger
from .local_session import LocalCycleResult, LocalTaskCycle


class EvidenceTrackingCycle:
    """Wrap LocalTaskCycle and reconstruct compact evidence after each boundary.

    The underlying V0.8 state machine remains the execution authority. Evidence is
    derived from its durable ledgers and workflow state, which means a later process
    can re-run sync_dispatch() after a crash without consuming another Task attempt.
    """

    def __init__(
        self,
        root: Path,
        cycle: LocalTaskCycle,
        *,
        evidence: ExecutionEvidenceLedger | None = None,
        dispatch_ledger: DispatchLedger | None = None,
    ):
        self.root = root
        self.cycle = cycle
        self.evidence = evidence or ExecutionEvidenceLedger(root)
        self.dispatch = dispatch_ledger or DispatchLedger(root)

    def __getattr__(self, name: str):
        return getattr(self.cycle, name)

    @staticmethod
    def _compact_profile(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        return {
            key: value.get(key)
            for key in ("surface", "family", "effort", "label")
            if value.get(key) is not None
        }

    def sync_dispatch(self, dispatch_id: str) -> None:
        session = self.cycle.sessions.get(dispatch_id)
        if not session:
            return
        task_id = str(session.get("task_id", "")).strip()
        if not task_id:
            return

        baseline = session.get("baseline") if isinstance(session.get("baseline"), dict) else {}
        self.evidence.record(
            task_id=task_id,
            dispatch_id=dispatch_id,
            kind="PREPARED",
            data={
                "difficulty": session.get("difficulty"),
                "requested_profile": self._compact_profile(session.get("requested_profile")),
                "baseline_message_count": baseline.get("message_count"),
                "baseline_latest_digest": baseline.get("latest_digest"),
                "before_git_digest": session.get("before_git_digest"),
            },
        )

        dispatch_entry = self.dispatch.get(dispatch_id)
        if isinstance(dispatch_entry, dict):
            status = str(dispatch_entry.get("status", ""))
            if status == "submitting":
                self.evidence.record(
                    task_id=task_id,
                    dispatch_id=dispatch_id,
                    kind="DISPATCH_RESERVED",
                    data={"ledger_status": "submitting"},
                )
            elif status == "submitted":
                self.evidence.record(
                    task_id=task_id,
                    dispatch_id=dispatch_id,
                    kind="SUBMITTED",
                    data={
                        "ledger_status": "submitted",
                        "backend": session.get("dispatch_backend"),
                    },
                )

        response_digest = session.get("response_digest")
        if response_digest:
            response_path = session.get("response_path")
            response_chars: int | None = None
            if response_path:
                path = self.root / str(response_path)
                if path.is_file():
                    try:
                        response_chars = len(path.read_text(encoding="utf-8"))
                    except OSError:
                        response_chars = None
            self.evidence.record(
                task_id=task_id,
                dispatch_id=dispatch_id,
                kind="RESPONSE_COLLECTED",
                data={
                    "response_digest": response_digest,
                    "response_path": response_path,
                    "response_chars": response_chars,
                },
            )

        raw_check = session.get("check")
        if isinstance(raw_check, dict):
            self.evidence.record(
                task_id=task_id,
                dispatch_id=dispatch_id,
                kind="CHECKED",
                data={
                    "ok": bool(raw_check.get("ok")),
                    "message": str(raw_check.get("message", "")),
                    "failure_type": raw_check.get("failure_type"),
                    "returncode": raw_check.get("returncode"),
                    "before_git_digest": session.get("before_git_digest"),
                    "after_git_digest": git_snapshot_digest(self.root),
                },
            )

        state = self.cycle.store.ensure_for_plan(self.cycle.plan)
        task_state = state.get("tasks", {}).get(task_id, {})
        if task_state.get("local_dispatch_id") == dispatch_id:
            self.evidence.record(
                task_id=task_id,
                dispatch_id=dispatch_id,
                kind="STATE_RECORDED",
                data={
                    "task_status": task_state.get("status"),
                    "attempts": task_state.get("attempts"),
                    "last_failure_type": task_state.get("last_failure_type"),
                    "workflow_status": state.get("status"),
                },
            )

        self.evidence.record(
            task_id=task_id,
            dispatch_id=dispatch_id,
            kind="SESSION_STATUS",
            data={"status": session.get("status")},
        )

    def run_next(self) -> LocalCycleResult:
        result = self.cycle.run_next()
        if result.dispatch_id:
            self.sync_dispatch(result.dispatch_id)
        return result
