from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .conversation_ui import DispatchLedger
from .execution_evidence import ExecutionEvidenceLedger
from .local_session import LocalSessionStore, LocalTaskCycle
from .response_monitor import ResponseBaseline


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    task_id: str
    dispatch_id: str | None
    status: str
    safe_to_retry: bool
    resumable: bool
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "dispatch_id": self.dispatch_id,
            "status": self.status,
            "safe_to_retry": self.safe_to_retry,
            "resumable": self.resumable,
            "message": self.message,
        }


class LocalRecoveryController:
    """Reconcile local crash boundaries without risking duplicate sends.

    Sender ordering is important: DispatchLedger.reserve() is durably written before
    the UI click is attempted. Therefore a PREPARED session with no dispatch-ledger
    entry never crossed the send reservation boundary and can be retired safely.

    A sticky `submitting` entry remains ambiguous unless calibrated response UI shows
    current-conversation activity. Ambiguity is never resolved by guessing.
    """

    def __init__(
        self,
        root: Path,
        cycle: LocalTaskCycle,
        *,
        dispatch_ledger: DispatchLedger | None = None,
        evidence: ExecutionEvidenceLedger | None = None,
    ):
        self.root = root
        self.cycle = cycle
        self.sessions: LocalSessionStore = cycle.sessions
        self.dispatch = dispatch_ledger or DispatchLedger(root)
        self.evidence = evidence or ExecutionEvidenceLedger(root)

    @staticmethod
    def _response_changed(session: dict[str, Any], snapshot) -> bool:
        baseline = ResponseBaseline.from_dict(session.get("baseline") or {})
        current = ResponseBaseline.from_messages(snapshot.messages)
        return bool(
            current.message_count > baseline.message_count
            or current.latest_digest != baseline.latest_digest
        )

    def reconcile_next(self) -> RecoveryResult:
        task = self.cycle.orchestrator.next_task()
        if task is None:
            return RecoveryResult("", None, "NO_TASK", False, False, "workflow has no unresolved task")

        active = self.sessions.active_for_task(task.id)
        if active is None:
            return RecoveryResult(
                task.id,
                None,
                "NO_ACTIVE_SESSION",
                True,
                False,
                "no active local session exists; a normal run may create a new dispatch",
            )

        dispatch_id, session = active
        session_status = str(session.get("status", ""))
        if session_status != "PREPARED":
            return RecoveryResult(
                task.id,
                dispatch_id,
                "ALREADY_RESUMABLE",
                False,
                True,
                f"session is {session_status}; use resume/run instead of PREPARED reconciliation",
            )

        entry = self.dispatch.get(dispatch_id)
        if entry is None:
            self.sessions.update(
                dispatch_id,
                status="ABORTED_SAFE_RETRY",
                recovery_reason="no dispatch reservation exists",
            )
            self.evidence.record(
                task_id=task.id,
                dispatch_id=dispatch_id,
                kind="RECOVERY_SAFE_RETRY",
                data={"reason": "no_dispatch_reservation"},
            )
            return RecoveryResult(
                task.id,
                dispatch_id,
                "SAFE_RETRY",
                True,
                False,
                "PREPARED session had no dispatch reservation; sender never crossed the click boundary",
            )

        ledger_status = str(entry.get("status", ""))
        if ledger_status == "submitted":
            self.sessions.update(
                dispatch_id,
                status="SUBMITTED",
                recovery_reason="dispatch ledger already confirmed submitted",
            )
            self.evidence.record(
                task_id=task.id,
                dispatch_id=dispatch_id,
                kind="RECOVERY_SUBMITTED",
                data={"reason": "dispatch_ledger_submitted"},
            )
            return RecoveryResult(
                task.id,
                dispatch_id,
                "RESUME",
                False,
                True,
                "dispatch ledger confirms submission; resume response collection without resending",
            )

        if ledger_status == "submitting":
            try:
                snapshot = self.cycle.monitor.source.snapshot()
            except (RuntimeError, ValueError) as exc:
                self.evidence.record(
                    task_id=task.id,
                    dispatch_id=dispatch_id,
                    kind="RECOVERY_AMBIGUOUS",
                    data={"reason": "response_source_unavailable", "error": str(exc)},
                )
                return RecoveryResult(
                    task.id,
                    dispatch_id,
                    "AMBIGUOUS",
                    False,
                    False,
                    f"dispatch is still ambiguous and response UI could not be verified: {exc}",
                )

            activity = bool(snapshot.busy or self._response_changed(session, snapshot))
            if activity:
                self.dispatch.mark_submitted(dispatch_id)
                self.sessions.update(
                    dispatch_id,
                    status="SUBMITTED",
                    recovery_reason="calibrated response UI shows post-baseline activity",
                )
                self.evidence.record(
                    task_id=task.id,
                    dispatch_id=dispatch_id,
                    kind="RECOVERY_SUBMITTED",
                    data={
                        "reason": "response_ui_activity",
                        "busy": bool(snapshot.busy),
                    },
                )
                return RecoveryResult(
                    task.id,
                    dispatch_id,
                    "RESUME",
                    False,
                    True,
                    "post-baseline response activity proves the canonical conversation advanced; resume without resending",
                )

            self.evidence.record(
                task_id=task.id,
                dispatch_id=dispatch_id,
                kind="RECOVERY_AMBIGUOUS",
                data={"reason": "submitting_without_post_baseline_activity"},
            )
            return RecoveryResult(
                task.id,
                dispatch_id,
                "AMBIGUOUS",
                False,
                False,
                "dispatch ledger is submitting but no calibrated post-baseline activity is visible; do not resend automatically",
            )

        self.evidence.record(
            task_id=task.id,
            dispatch_id=dispatch_id,
            kind="RECOVERY_AMBIGUOUS",
            data={"reason": "unexpected_dispatch_status", "status": ledger_status},
        )
        return RecoveryResult(
            task.id,
            dispatch_id,
            "AMBIGUOUS",
            False,
            False,
            f"unexpected dispatch ledger status {ledger_status!r}; manual reconciliation required",
        )
