from __future__ import annotations

import json

from dev_task_router.e2e_calibration import EndToEndCalibrationRecorder
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.mode_switch import RequestedProfile, SwitchResult
from dev_task_router.models import ModelLevel, TaskSpec
from dev_task_router.profile_calibration import ProfileCalibrationRegistry
from dev_task_router.ui_fingerprint import UIFingerprint, UIFingerprintStore


def _fingerprint() -> UIFingerprint:
    return UIFingerprint.from_rows(
        {"mode": [{"name": "Medium", "control_type": "MenuItem", "automation_id": "medium"}]},
        tracked_labels={"mode.effort.medium": ("Medium",)},
        platform="win32",
    )


def _switch(level: ModelLevel = ModelLevel.MEDIUM, effort: str = "medium") -> SwitchResult:
    requested = RequestedProfile("chat", level, "sol", effort, f"Sol {effort}")
    return SwitchResult(
        requested=requested,
        actual_family="sol",
        actual_effort=effort,
        verified=True,
        backend="fake-windows-uia",
        changed=True,
        message="verified",
    )


def _session(tmp_path, *, task_id: str, dispatch_id: str, level: str = "MEDIUM") -> None:
    path = tmp_path / ".autodev" / "local-sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "sessions": {
                    dispatch_id: {
                        "task_id": task_id,
                        "status": "PASSED",
                        "difficulty": level,
                        "requested_profile": {
                            "surface": "chat",
                            "family": "sol",
                            "effort": level.lower(),
                            "label": f"Sol {level.title()}",
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _base_evidence(ledger: ExecutionEvidenceLedger, *, task_id: str, dispatch_id: str) -> None:
    ledger.record(task_id=task_id, dispatch_id=dispatch_id, kind="SUBMITTED", data={"backend": "uia"})
    ledger.record(
        task_id=task_id,
        dispatch_id=dispatch_id,
        kind="RESPONSE_COLLECTED",
        data={"response_digest": "abc"},
    )
    ledger.record(
        task_id=task_id,
        dispatch_id=dispatch_id,
        kind="CHECKED",
        data={"ok": True, "message": "checks passed"},
    )
    ledger.record(
        task_id=task_id,
        dispatch_id=dispatch_id,
        kind="STATE_RECORDED",
        data={"task_status": "PASSED", "workflow_status": "READY"},
    )


def test_e2e_calibration_requires_full_durable_pass_evidence(tmp_path) -> None:
    task = TaskSpec(id="impl", title="Implement", prompt="Implement", kind="normal_code")
    dispatch_id = "dispatch-medium"
    fingerprint = _fingerprint()
    UIFingerprintStore(tmp_path).save(fingerprint)
    registry = ProfileCalibrationRegistry(tmp_path)
    registry.record_verified_switch(_switch(), ui_fingerprint=fingerprint.digest)
    _session(tmp_path, task_id=task.id, dispatch_id=dispatch_id)
    ledger = ExecutionEvidenceLedger(tmp_path)

    ledger.record(task_id=task.id, dispatch_id=dispatch_id, kind="SUBMITTED", data={})
    pending = EndToEndCalibrationRecorder(tmp_path, registry=registry, evidence=ledger).try_record(
        task, dispatch_id
    )
    assert pending.recorded is False
    assert "RESPONSE_COLLECTED" in pending.message

    _base_evidence(ledger, task_id=task.id, dispatch_id=dispatch_id)
    recorded = EndToEndCalibrationRecorder(tmp_path, registry=registry, evidence=ledger).try_record(
        task, dispatch_id
    )
    assert recorded.recorded is True
    assert recorded.record is not None
    assert recorded.record.evidence_dispatch_id == dispatch_id
    assert registry.coverage(fingerprint.digest).e2e_levels == ("MEDIUM",)
    assert any(event.kind == "PROFILE_E2E_CALIBRATED" for event in ledger.events_for_dispatch(dispatch_id))


def test_review_task_requires_reviewer_pass_before_e2e_calibration(tmp_path) -> None:
    task = TaskSpec(
        id="reviewed",
        title="Reviewed change",
        prompt="Implement",
        kind="normal_code",
        review=True,
    )
    dispatch_id = "dispatch-reviewed"
    fingerprint = _fingerprint()
    UIFingerprintStore(tmp_path).save(fingerprint)
    registry = ProfileCalibrationRegistry(tmp_path)
    registry.record_verified_switch(_switch(), ui_fingerprint=fingerprint.digest)
    _session(tmp_path, task_id=task.id, dispatch_id=dispatch_id)
    ledger = ExecutionEvidenceLedger(tmp_path)
    _base_evidence(ledger, task_id=task.id, dispatch_id=dispatch_id)

    recorder = EndToEndCalibrationRecorder(tmp_path, registry=registry, evidence=ledger)
    before_review = recorder.try_record(task, dispatch_id)
    assert before_review.recorded is False
    assert "Reviewer PASS" in before_review.message

    ledger.record(
        task_id=task.id,
        dispatch_id=dispatch_id,
        kind="REVIEWED",
        data={"verdict": "PASS", "ok": True},
    )
    after_review = recorder.try_record(task, dispatch_id)
    assert after_review.recorded is True


def test_e2e_calibration_rejects_executed_profile_mismatch(tmp_path) -> None:
    task = TaskSpec(id="impl", title="Implement", prompt="Implement", kind="normal_code")
    dispatch_id = "dispatch-medium"
    fingerprint = _fingerprint()
    UIFingerprintStore(tmp_path).save(fingerprint)
    registry = ProfileCalibrationRegistry(tmp_path)
    registry.record_verified_switch(_switch(), ui_fingerprint=fingerprint.digest)
    _session(tmp_path, task_id=task.id, dispatch_id=dispatch_id)
    data = json.loads((tmp_path / ".autodev" / "local-sessions.json").read_text(encoding="utf-8"))
    data["sessions"][dispatch_id]["requested_profile"]["family"] = "other"
    (tmp_path / ".autodev" / "local-sessions.json").write_text(json.dumps(data), encoding="utf-8")
    ledger = ExecutionEvidenceLedger(tmp_path)
    _base_evidence(ledger, task_id=task.id, dispatch_id=dispatch_id)

    result = EndToEndCalibrationRecorder(tmp_path, registry=registry, evidence=ledger).try_record(
        task, dispatch_id
    )
    assert result.recorded is False
    assert "family" in result.message
