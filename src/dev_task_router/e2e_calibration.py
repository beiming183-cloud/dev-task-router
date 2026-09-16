from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .execution_evidence import ExecutionEvidenceLedger
from .local_session import LocalSessionStore
from .models import ModelLevel, TaskSpec
from .profile_calibration import ProfileCalibrationRecord, ProfileCalibrationRegistry
from .ui_fingerprint import UIFingerprintStore


@dataclass(frozen=True, slots=True)
class EndToEndCalibrationResult:
    recorded: bool
    level: str | None
    dispatch_id: str
    message: str
    record: ProfileCalibrationRecord | None = None

    def to_dict(self) -> dict:
        return {
            "recorded": self.recorded,
            "level": self.level,
            "dispatch_id": self.dispatch_id,
            "message": self.message,
            "record": self.record.to_dict() if self.record else None,
        }


class EndToEndCalibrationRecorder:
    """Promote a live switch calibration to end-to-end only from durable evidence.

    This is deliberately non-authoritative for Task state: failure to record calibration
    never turns a Checker/Reviewer PASS back into a Task failure. It only means V1.0
    live readiness remains incomplete.
    """

    def __init__(
        self,
        root: Path,
        *,
        registry: ProfileCalibrationRegistry | None = None,
        evidence: ExecutionEvidenceLedger | None = None,
        sessions: LocalSessionStore | None = None,
    ):
        self.root = root.resolve()
        self.registry = registry or ProfileCalibrationRegistry(self.root)
        self.evidence = evidence or ExecutionEvidenceLedger(self.root)
        self.sessions = sessions or LocalSessionStore(self.root)
        self.fingerprints = UIFingerprintStore(self.root)

    def _verify_dispatch_evidence(
        self,
        task: TaskSpec,
        dispatch_id: str,
    ) -> tuple[bool, str]:
        if not self.evidence.verify_chain():
            return False, "execution evidence chain is invalid"
        events = self.evidence.events_for_dispatch(dispatch_id)
        if not events:
            return False, "no execution evidence exists for the dispatch"
        if any(event.task_id != task.id for event in events):
            return False, "dispatch evidence contains a mismatched task identity"

        kinds = {event.kind for event in events}
        for required in ("SUBMITTED", "RESPONSE_COLLECTED", "CHECKED", "STATE_RECORDED"):
            if required not in kinds:
                return False, f"dispatch is missing required {required} evidence"

        checked = [event for event in events if event.kind == "CHECKED"]
        if not checked or not any(bool(event.data.get("ok")) for event in checked):
            return False, "dispatch does not contain a successful Checker result"

        states = [event for event in events if event.kind == "STATE_RECORDED"]
        if not any(str(event.data.get("task_status")) == "PASSED" for event in states):
            return False, "dispatch has no durable PASSED workflow state"

        if task.review:
            reviews = [event for event in events if event.kind == "REVIEWED"]
            if not any(str(event.data.get("verdict", "")).upper() == "PASS" for event in reviews):
                return False, "task requires independent Reviewer PASS evidence"
        return True, "dispatch has complete end-to-end execution evidence"

    def validate_record(
        self,
        task: TaskSpec,
        record: ProfileCalibrationRecord,
    ) -> tuple[bool, str]:
        if not record.end_to_end_verified or not record.evidence_dispatch_id:
            return False, "profile has no end-to-end dispatch evidence"
        baseline = self.fingerprints.load()
        if baseline is None:
            return False, "UI fingerprint baseline is missing"
        if baseline.digest != record.ui_fingerprint:
            return False, "profile end-to-end evidence belongs to a stale UI fingerprint"

        session = self.sessions.get(record.evidence_dispatch_id)
        if not isinstance(session, dict):
            return False, "end-to-end calibration dispatch session is missing"
        if session.get("task_id") != task.id:
            return False, "end-to-end calibration session belongs to another task"
        if str(session.get("difficulty", "")).upper() != record.level.value:
            return False, "session difficulty does not match calibrated level"
        requested = session.get("requested_profile")
        if not isinstance(requested, dict):
            return False, "session requested profile is missing"
        if str(requested.get("family", "")) != record.family:
            return False, "session family does not match calibrated family"
        if requested.get("effort") != record.effort:
            return False, "session effort does not match calibrated effort"
        return self._verify_dispatch_evidence(task, record.evidence_dispatch_id)

    def try_record(
        self,
        task: TaskSpec,
        dispatch_id: str,
    ) -> EndToEndCalibrationResult:
        dispatch_id = dispatch_id.strip()
        if not dispatch_id:
            return EndToEndCalibrationResult(False, None, "", "dispatch_id is empty")
        try:
            session = self.sessions.get(dispatch_id)
            if not isinstance(session, dict):
                return EndToEndCalibrationResult(
                    False, None, dispatch_id, "local execution session is missing"
                )
            if session.get("task_id") != task.id:
                return EndToEndCalibrationResult(
                    False, None, dispatch_id, "session belongs to another task"
                )
            level = ModelLevel(str(session.get("difficulty", "")).upper())
            if level == ModelLevel.NONE:
                return EndToEndCalibrationResult(
                    False, level.value, dispatch_id, "NONE has no live profile calibration"
                )
            requested = session.get("requested_profile")
            if not isinstance(requested, dict):
                return EndToEndCalibrationResult(
                    False, level.value, dispatch_id, "session requested profile is missing"
                )
            family = str(requested.get("family", "")).strip()
            effort = requested.get("effort")
            if effort is not None:
                effort = str(effort).strip()

            ok, message = self._verify_dispatch_evidence(task, dispatch_id)
            if not ok:
                return EndToEndCalibrationResult(False, level.value, dispatch_id, message)

            baseline = self.fingerprints.load()
            if baseline is None:
                return EndToEndCalibrationResult(
                    False,
                    level.value,
                    dispatch_id,
                    "no UI fingerprint baseline exists for end-to-end calibration",
                )
            record = self.registry.mark_end_to_end_verified(
                level,
                ui_fingerprint=baseline.digest,
                dispatch_id=dispatch_id,
                family=family,
                effort=effort,
            )
            self.evidence.record(
                task_id=task.id,
                dispatch_id=dispatch_id,
                kind="PROFILE_E2E_CALIBRATED",
                data={
                    "level": level.value,
                    "family": family,
                    "effort": effort,
                    "ui_fingerprint": baseline.digest,
                },
            )
            return EndToEndCalibrationResult(
                True,
                level.value,
                dispatch_id,
                "end-to-end profile calibration recorded from verified execution evidence",
                record,
            )
        except (OSError, ValueError) as exc:
            return EndToEndCalibrationResult(
                False,
                None,
                dispatch_id,
                f"end-to-end calibration remains pending: {exc}",
            )
