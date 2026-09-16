from __future__ import annotations

import yaml

from dev_task_router.config import write_default_files
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


def test_release_ready_requires_matching_fingerprint_and_three_e2e_profiles(tmp_path) -> None:
    write_default_files(tmp_path, "demo")
    _configure_live_files(tmp_path)
    fingerprint = _fingerprint()
    UIFingerprintStore(tmp_path).save(fingerprint)

    registry = ProfileCalibrationRegistry(tmp_path)
    for level, effort in (
        (ModelLevel.LOW, "low"),
        (ModelLevel.MEDIUM, "medium"),
        (ModelLevel.HIGH, "high"),
    ):
        registry.record_verified_switch(
            _switch(level, effort), ui_fingerprint=fingerprint.digest
        )
        registry.mark_end_to_end_verified(
            level,
            ui_fingerprint=fingerprint.digest,
            dispatch_id=f"dispatch-{effort}",
        )

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
