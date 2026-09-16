from __future__ import annotations

import hashlib
import json
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

    ACTIVE_STATUSES = {
        "PREPARED",
        "SUBMITTED",
        "WAITING_RESPONSE",
        "COLLECTED",
        "CHECKED",
        "REVIEW_REQUIRED",
    }

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

    def _latest_active_any(self) -> tuple[str, dict[str, Any]] | None:
        if not self.sessions.path.exists():
            return None
        data = json.loads(self.sessions.path.read_text(encoding="utf-8"))
        sessions = data.get("sessions", {}) if isinstance(data, dict) else {}
        if not isinstance(sessions, dict):
            raise ValueError("local-sessions.json must contain a sessions mapping")
        candidates = [
            (dispatch_id, item)
            for dispatch_id, item in sessions.items()
            if isinstance(item, dict) and item.get("status") in self.ACTIVE_STATUSES
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda pair: str(pair[1].get("updated_at", "")), reverse=True)
        return candidates[0]

    def _recover_terminal_state_session(self) -> RecoveryResult | None:
        active = self._latest_active_any()
        if active is None:
            return None
        dispatch_id, session = active
        task_id = str(session.get("task_id", "")).strip()
        if not task_id:
            return None
        state = self.cycle.store.ensure_for_plan(self.cycle.plan)
        item = state.get("tasks", {}).get(task_id)
        if not isinstance(item, dict):
            return None
        if item.get("local_dispatch_id") != dispatch_id:
            return None
        if item.get("status") != "PASSED":
            return None

        self.sessions.update(
            dispatch_id,
            status="PASSED",
            recovery_reason="workflow PASS was durable before session terminal update",
        )
        self.evidence.record(
            task_id=task_id,
            dispatch_id=dispatch_id,
            kind="RECOVERY_STATE_TERMINAL",
            data={
                "task_status": "PASSED",
                "attempts": item.get("attempts"),
                "previous_session_status": session.get("status"),
            },
        )
        return RecoveryResult(
            task_id,
            dispatch_id,
            "RECOVERED_STATE",
            False,
            False,
            "workflow PASS already existed; session terminal state was repaired without another attempt",
        )

    def _recover_written_response(
        self,
        task_id: str,
        dispatch_id: str,
        session: dict[str, Any],
    ) -> RecoveryResult | None:
        status = str(session.get("status", ""))
        if status not in {"SUBMITTED", "WAITING_RESPONSE"}:
            return None
        if session.get("response_digest") or session.get("response_path"):
            return None

        path = self.sessions.response_dir / f"{dispatch_id}.txt"
        if not path.is_file():
            return None
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            self.evidence.record(
                task_id=task_id,
                dispatch_id=dispatch_id,
                kind="RECOVERY_AMBIGUOUS",
                data={"reason": "orphan_response_unreadable", "error": str(exc)},
            )
            return RecoveryResult(
                task_id,
                dispatch_id,
                "AMBIGUOUS",
                False,
                False,
                f"orphan response file exists but could not be verified: {exc}",
            )

        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        relative = path.relative_to(self.root).as_posix()
        self.sessions.update(
            dispatch_id,
            status="COLLECTED",
            response_path=relative,
            response_digest=digest,
            recovery_reason="response file was durable before session metadata update",
        )
        self.evidence.record(
            task_id=task_id,
            dispatch_id=dispatch_id,
            kind="RECOVERY_RESPONSE_FILE",
            data={
                "response_digest": digest,
                "response_chars": len(text),
                "response_path": relative,
            },
        )
        return RecoveryResult(
            task_id,
            dispatch_id,
            "RESUME",
            False,
            True,
            "durable response file recovered into COLLECTED state; resume Checker without resending",
        )

    def reconcile_next(self) -> RecoveryResult:
        task = self.cycle.orchestrator.next_task()
        if task is None:
            repaired = self._recover_terminal_state_session()
            if repaired is not None:
                return repaired
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
        written_response = self._recover_written_response(task.id, dispatch_id, session)
        if written_response is not None:
            return written_response

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
