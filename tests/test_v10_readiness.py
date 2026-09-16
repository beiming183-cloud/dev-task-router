from __future__ import annotations

import hashlib
import json

import yaml

from dev_task_router.config import write_default_files
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.mode_switch import RequestedProfile, SwitchResult
from dev_task_router.models import ModelLevel
from dev_task_router.profile_calibration import ProfileCalibrationRegistry
from dev_task_router.readiness import V1ReadinessEvaluator
from dev_task_router.ui_fingerprint import UIFingerprint, UIFingerprintStore


def _switch(level: ModelLevel, effort: str) -> SwitchResult:
    requested = RequestedProfile(
        surface="chat",
        level=level,
        family="sol",
        effort=effort,
        label=f"5.6 Sol {effort.title()}",
    )
    return SwitchResult(
        requested=requested,
        actual_family="sol",
        actual_effort=effort,
        verified=True,
        backend="fake-windows-uia",
        changed=True,
        message="verified",
    )


def _configure_live_files(tmp_path) -> None:
    runtime = tmp_path / ".autodev"
    (runtime / "local-switch.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "enabled": True,
                "backend": "windows-uia",
                "window": {"title_regex": ".*ChatGPT.*"},
                "selector": {"open_labels": ["Model"]},
                "family_labels": {"sol": ["Sol"]},
                "effort_labels": {
                    "low": ["Low"],
                    "medium": ["Medium"],
                    "high": ["High"],
                },
                "verify_labels": {
                    "low": ["Low"],
                    "medium": ["Medium"],
                    "high": ["High"],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    (runtime / "local-conversation.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "enabled": True,
                "backend": "windows-uia",
                "window": {"title_regex": ".*ChatGPT.*"},
                "composer": {"labels": ["Message"], "control_types": ["Edit"]},
                "send": {"labels": ["Send"], "control_types": ["Button"]},
                "response": {
                    "enabled": True,
                    "busy_labels": ["Stop"],
                    "busy_control_types": ["Button"],
                    "assistant_control_types": ["Text"],
                    "assistant_automation_id_regex": "assistant-.*",
                    "poll_interval_seconds": 1.0,
                    "timeout_seconds": 60.0,
                    "stable_polls": 2,
                },
                "limits": {"max_prompt_chars": 60000},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _write_calibration_plan(tmp_path) -> None:
    tasks = []
    for level in ("low", "medium", "high"):
        tasks.append(
            {
                "id": f"task-{level}",
                "title": f"Calibrate {level}",
                "kind": "normal_code",
                "prompt": f"Perform a bounded {level} calibration task",
                "max_attempts": 1,
            }
        )
    (tmp_path / ".autodev" / "plan.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 3,
                "project": "demo",
                "stages": [
                    {
                        "id": "calibration",
                        "steps": [{"id": "profiles", "tasks": tasks}],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def _fingerprint() -> UIFingerprint:
    return UIFingerprint.from_rows(
        {
            "mode": [
                {"name": "Model", "control_type": "Button", "automation_id": "model"},
                {"name": "Low", "control_type": "MenuItem", "automation_id": "low"},
                {"name": "Medium", "control_type": "MenuItem", "automation_id": "medium"},
                {"name": "High", "control_type": "MenuItem", "automation_id": "high"},
            ],
            "conversation": [
                {"name": "Message", "control_type": "Edit", "automation_id": "composer"},
                {"name": "Send", "control_type": "Button", "automation_id": "send"},
                {"name": "Stop", "control_type": "Button", "automation_id": "busy"},
            ],
        },
        tracked_labels={
            "mode.selector": ("Model",),
            "mode.effort.low": ("Low",),
            "mode.effort.medium": ("Medium",),
            "mode.effort.high": ("High",),
            "conversation.composer": ("Message",),
            "conversation.send": ("Send",),
            "response.busy": ("Stop",),
        },
        platform="win32",
    )


def _write_e2e_runtime(tmp_path, registry: ProfileCalibrationRegistry, fingerprint: UIFingerprint) -> None:
    runtime = tmp_path / ".autodev"
    response_dir = runtime / "local-responses"
    response_dir.mkdir(parents=True, exist_ok=True)
    sessions: dict[str, dict] = {}
    ledger = ExecutionEvidenceLedger(tmp_path)

    for level, effort in (
        (ModelLevel.LOW, "low"),
        (ModelLevel.MEDIUM, "medium"),
        (ModelLevel.HIGH, "high"),
    ):
        task_id = f"task-{effort}"
        dispatch_id = f"dispatch-{effort}"
        text = f"assistant response for {effort}"
        response_path = response_dir / f"{dispatch_id}.txt"
        response_path.write_text(text, encoding="utf-8")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        sessions[dispatch_id] = {
            "task_id": task_id,
            "status": "PASSED",
            "difficulty": level.value,
            "requested_profile": {
                "surface": "chat",
                "family": "sol",
                "effort": effort,
                "label": f"5.6 Sol {effort.title()}",
            },
            "response_path": response_path.relative_to(tmp_path).as_posix(),
            "response_digest": digest,
            "check": {"ok": True, "message": "checks passed", "failure_type": None, "returncode": 0},
        }
        ledger.record(task_id=task_id, dispatch_id=dispatch_id, kind="SUBMITTED", data={"backend": "uia"})
        ledger.record(
            task_id=task_id,
            dispatch_id=dispatch_id,
            kind="RESPONSE_COLLECTED",
            data={"response_digest": digest},
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
        registry.record_verified_switch(
            _switch(level, effort), ui_fingerprint=fingerprint.digest
        )
        registry.mark_end_to_end_verified(
            level,
            ui_fingerprint=fingerprint.digest,
            dispatch_id=dispatch_id,
            family="sol",
            effort=effort,
        )

    (runtime / "local-sessions.json").write_text(
        json.dumps({"version": 1, "sessions": sessions}),
        encoding="utf-8",
    )


def test_readiness_does_not_confuse_automated_green_with_live_windows_green(tmp_path) -> None:
    write_default_files(tmp_path, "demo")
    report = V1ReadinessEvaluator(tmp_path).run()

    assert report.automated_ready is True
    assert report.live_windows_ready is False
    assert report.release_ready is False
    live = {check.code: check for check in report.checks if check.scope == "live_windows"}
    assert live["WINDOWS_UI_FINGERPRINT"].status == "PENDING"
    assert live["WINDOWS_PROFILE_SWITCH_CALIBRATION"].status == "PENDING"
    assert live["WINDOWS_END_TO_END_CALIBRATION"].status == "PENDING"


def test_release_ready_requires_matching_fingerprint_and_durable_three_profile_evidence(tmp_path) -> None:
    write_default_files(tmp_path, "demo")
    _write_calibration_plan(tmp_path)
    _configure_live_files(tmp_path)
    fingerprint = _fingerprint()
    UIFingerprintStore(tmp_path).save(fingerprint)
    registry = ProfileCalibrationRegistry(tmp_path)
    _write_e2e_runtime(tmp_path, registry, fingerprint)

    report = V1ReadinessEvaluator(tmp_path).run(
        current_ui_fingerprint=fingerprint.digest
    )
    assert report.automated_ready is True
    assert report.live_windows_ready is True
    assert report.release_ready is True
    assert all(check.status == "PASS" for check in report.checks)

    drifted = V1ReadinessEvaluator(tmp_path).run(current_ui_fingerprint="different-ui")
    assert drifted.automated_ready is True
    assert drifted.live_windows_ready is False
    assert drifted.release_ready is False
    status = {check.code: check.status for check in drifted.checks}
    assert status["WINDOWS_UI_FINGERPRINT"] == "BLOCKED"


def test_tampered_e2e_registry_cannot_make_release_ready(tmp_path) -> None:
    write_default_files(tmp_path, "demo")
    _write_calibration_plan(tmp_path)
    _configure_live_files(tmp_path)
    fingerprint = _fingerprint()
    UIFingerprintStore(tmp_path).save(fingerprint)
    registry = ProfileCalibrationRegistry(tmp_path)
    _write_e2e_runtime(tmp_path, registry, fingerprint)

    data = json.loads(registry.path.read_text(encoding="utf-8"))
    data["profiles"]["HIGH"]["evidence_dispatch_id"] = "made-up-dispatch"
    registry.path.write_text(json.dumps(data), encoding="utf-8")

    report = V1ReadinessEvaluator(tmp_path).run(current_ui_fingerprint=fingerprint.digest)
    status = {check.code: check for check in report.checks}
    assert report.release_ready is False
    assert status["WINDOWS_END_TO_END_CALIBRATION"].status == "BLOCKED"
