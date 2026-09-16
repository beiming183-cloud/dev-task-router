from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import STATE_FILE, autodev_dir
from .execution_evidence import ExecutionEvidenceLedger


@dataclass(frozen=True, slots=True)
class AuditIssue:
    severity: str
    code: str
    message: str
    task_id: str | None = None
    dispatch_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "task_id": self.task_id,
            "dispatch_id": self.dispatch_id,
        }


@dataclass(frozen=True, slots=True)
class ExecutionAuditReport:
    issues: tuple[AuditIssue, ...]
    evidence_events: int
    session_count: int
    dispatch_count: int

    @property
    def errors(self) -> tuple[AuditIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "ERROR")

    @property
    def warnings(self) -> tuple[AuditIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity == "WARNING")

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "evidence_events": self.evidence_events,
            "session_count": self.session_count,
            "dispatch_count": self.dispatch_count,
            "issues": [issue.to_dict() for issue in self.issues],
        }


class LocalExecutionAuditor:
    """Cross-check durable V0.8/V0.9 runtime state without mutating it."""

    MODEL_POST_SEND_STATUSES = {
        "SUBMITTED",
        "WAITING_RESPONSE",
        "COLLECTED",
        "CHECKED",
        "REVIEW_REQUIRED",
        "PASSED",
        "CHECK_FAILED",
        "FAILED",
        "BLOCKED",
    }
    RESPONSE_REQUIRED_STATUSES = {
        "COLLECTED",
        "CHECKED",
        "REVIEW_REQUIRED",
        "PASSED",
        "CHECK_FAILED",
        "FAILED",
        "BLOCKED",
    }

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.runtime = autodev_dir(self.root)
        self.evidence = ExecutionEvidenceLedger(self.root)

    @staticmethod
    def _mapping_file(path: Path, key: str) -> dict[str, Any]:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get(key), dict):
            raise ValueError(f"{path.name} must contain a {key} mapping")
        return data[key]

    def _safe_runtime_path(self, relative: str) -> Path | None:
        try:
            candidate = (self.root / relative).resolve()
            candidate.relative_to(self.root)
        except (ValueError, OSError):
            return None
        return candidate

    @staticmethod
    def _response_digest(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def run(self) -> ExecutionAuditReport:
        issues: list[AuditIssue] = []

        try:
            events = self.evidence.events()
            if not self.evidence.verify_chain():
                issues.append(
                    AuditIssue(
                        "ERROR",
                        "EVIDENCE_CHAIN_INVALID",
                        "execution evidence hash chain or sequence is invalid",
                    )
                )
        except (ValueError, OSError) as exc:
            events = ()
            issues.append(
                AuditIssue(
                    "ERROR",
                    "EVIDENCE_UNREADABLE",
                    f"execution evidence could not be read: {exc}",
                )
            )

        try:
            sessions = self._mapping_file(self.runtime / "local-sessions.json", "sessions")
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            sessions = {}
            issues.append(
                AuditIssue("ERROR", "SESSIONS_UNREADABLE", f"local sessions could not be read: {exc}")
            )

        try:
            dispatches = self._mapping_file(self.runtime / "local-dispatch.json", "entries")
        except (ValueError, json.JSONDecodeError, OSError) as exc:
            dispatches = {}
            issues.append(
                AuditIssue("ERROR", "DISPATCH_LEDGER_UNREADABLE", f"dispatch ledger could not be read: {exc}")
            )

        state: dict[str, Any] = {}
        state_path = self.runtime / STATE_FILE
        if state_path.exists():
            try:
                loaded = json.loads(state_path.read_text(encoding="utf-8"))
                if not isinstance(loaded, dict) or not isinstance(loaded.get("tasks"), dict):
                    raise ValueError("state must contain a tasks mapping")
                state = loaded
            except (ValueError, json.JSONDecodeError, OSError) as exc:
                issues.append(
                    AuditIssue("ERROR", "STATE_UNREADABLE", f"workflow state could not be read: {exc}")
                )

        event_by_dispatch: dict[str, list[Any]] = {}
        event_by_task: dict[str, list[Any]] = {}
        for event in events:
            event_by_task.setdefault(event.task_id, []).append(event)
            if event.dispatch_id:
                event_by_dispatch.setdefault(event.dispatch_id, []).append(event)

        for dispatch_id, raw in sessions.items():
            if not isinstance(raw, dict):
                issues.append(
                    AuditIssue("ERROR", "SESSION_INVALID", "session entry is not a mapping", dispatch_id=dispatch_id)
                )
                continue
            task_id = str(raw.get("task_id", "")) or None
            status = str(raw.get("status", ""))
            ledger = dispatches.get(dispatch_id)

            if status == "PREPARED":
                if ledger is None:
                    issues.append(
                        AuditIssue(
                            "WARNING",
                            "SAFE_RETRY_AVAILABLE",
                            "PREPARED session has no dispatch reservation; recover can retire it safely",
                            task_id,
                            dispatch_id,
                        )
                    )
                elif isinstance(ledger, dict) and ledger.get("status") == "submitting":
                    issues.append(
                        AuditIssue(
                            "WARNING",
                            "AMBIGUOUS_SEND",
                            "PREPARED session is reserved as submitting; calibrated recovery evidence is required",
                            task_id,
                            dispatch_id,
                        )
                    )
                elif isinstance(ledger, dict) and ledger.get("status") == "submitted":
                    issues.append(
                        AuditIssue(
                            "WARNING",
                            "RESUME_AVAILABLE",
                            "dispatch ledger confirms submitted while session is PREPARED; recover can resume it",
                            task_id,
                            dispatch_id,
                        )
                    )

            if status in self.MODEL_POST_SEND_STATUSES and ledger is not None:
                if not isinstance(ledger, dict) or ledger.get("status") != "submitted":
                    issues.append(
                        AuditIssue(
                            "ERROR",
                            "DISPATCH_STATUS_CONFLICT",
                            f"session is {status} but dispatch ledger is not submitted",
                            task_id,
                            dispatch_id,
                        )
                    )

            if status in self.RESPONSE_REQUIRED_STATUSES:
                digest = str(raw.get("response_digest") or "")
                response_path = str(raw.get("response_path") or "")
                if not digest or not response_path:
                    issues.append(
                        AuditIssue(
                            "ERROR",
                            "RESPONSE_EVIDENCE_MISSING",
                            f"session status {status} requires response path and digest",
                            task_id,
                            dispatch_id,
                        )
                    )
                else:
                    path = self._safe_runtime_path(response_path)
                    if path is None:
                        issues.append(
                            AuditIssue(
                                "ERROR",
                                "RESPONSE_PATH_UNSAFE",
                                "response path escapes the project root",
                                task_id,
                                dispatch_id,
                            )
                        )
                    elif not path.is_file():
                        issues.append(
                            AuditIssue(
                                "ERROR",
                                "RESPONSE_FILE_MISSING",
                                f"response file is missing: {response_path}",
                                task_id,
                                dispatch_id,
                            )
                        )
                    else:
                        try:
                            actual = self._response_digest(path)
                        except (OSError, UnicodeError) as exc:
                            issues.append(
                                AuditIssue(
                                    "ERROR",
                                    "RESPONSE_FILE_UNREADABLE",
                                    f"response file could not be read: {exc}",
                                    task_id,
                                    dispatch_id,
                                )
                            )
                        else:
                            if actual != digest:
                                issues.append(
                                    AuditIssue(
                                        "ERROR",
                                        "RESPONSE_DIGEST_MISMATCH",
                                        "response file content does not match the recorded digest",
                                        task_id,
                                        dispatch_id,
                                    )
                                )

            if status in {"CHECKED", "REVIEW_REQUIRED", "PASSED", "CHECK_FAILED", "FAILED", "BLOCKED"}:
                if not isinstance(raw.get("check"), dict):
                    issues.append(
                        AuditIssue(
                            "ERROR",
                            "CHECK_EVIDENCE_MISSING",
                            f"session status {status} requires a durable check record",
                            task_id,
                            dispatch_id,
                        )
                    )

        for dispatch_id, raw in dispatches.items():
            if dispatch_id not in sessions and isinstance(raw, dict) and raw.get("status") in {"submitting", "submitted"}:
                issues.append(
                    AuditIssue(
                        "WARNING",
                        "ORPHAN_DISPATCH_LEDGER",
                        "dispatch ledger entry has no corresponding local session",
                        str(raw.get("task_id") or "") or None,
                        dispatch_id,
                    )
                )

        for task_id, raw in state.get("tasks", {}).items():
            if not isinstance(raw, dict):
                continue
            dispatch_id = raw.get("local_dispatch_id")
            if dispatch_id:
                dispatch_id = str(dispatch_id)
                session = sessions.get(dispatch_id)
                if not isinstance(session, dict):
                    issues.append(
                        AuditIssue(
                            "ERROR",
                            "STATE_SESSION_MISSING",
                            "workflow task references a local dispatch with no session",
                            task_id,
                            dispatch_id,
                        )
                    )
                elif str(session.get("task_id", "")) != task_id:
                    issues.append(
                        AuditIssue(
                            "ERROR",
                            "STATE_SESSION_TASK_CONFLICT",
                            "workflow task and local session disagree on task_id",
                            task_id,
                            dispatch_id,
                        )
                    )

                dispatch_events = event_by_dispatch.get(dispatch_id, [])
                state_events = [event for event in dispatch_events if event.kind == "STATE_RECORDED"]
                if not state_events:
                    issues.append(
                        AuditIssue(
                            "WARNING",
                            "EVIDENCE_SYNC_PENDING",
                            "workflow state is durable but STATE_RECORDED evidence has not been reconstructed yet",
                            task_id,
                            dispatch_id,
                        )
                    )
                else:
                    latest = state_events[-1].data
                    if latest.get("task_status") != raw.get("status") or latest.get("attempts") != raw.get("attempts"):
                        issues.append(
                            AuditIssue(
                                "WARNING",
                                "EVIDENCE_STATE_STALE",
                                "latest STATE_RECORDED evidence does not match current workflow state",
                                task_id,
                                dispatch_id,
                            )
                        )

            route = raw.get("route")
            if isinstance(route, dict) and route.get("level") == "NONE" and raw.get("status") in {"PASSED", "FAILED", "BLOCKED"}:
                deterministic_state = [
                    event
                    for event in event_by_task.get(task_id, [])
                    if event.kind == "STATE_RECORDED" and event.data.get("execution") == "deterministic"
                ]
                if not deterministic_state:
                    issues.append(
                        AuditIssue(
                            "WARNING",
                            "DETERMINISTIC_EVIDENCE_SYNC_PENDING",
                            "terminal NONE task has no V0.9 deterministic STATE_RECORDED evidence",
                            task_id,
                        )
                    )

        return ExecutionAuditReport(
            issues=tuple(issues),
            evidence_events=len(events),
            session_count=len(sessions),
            dispatch_count=len(dispatches),
        )
