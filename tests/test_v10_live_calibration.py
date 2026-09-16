from __future__ import annotations

import pytest

from dev_task_router.live_calibration import LiveProfileCalibrator
from dev_task_router.mode_switch import RequestedProfile, SwitchResult
from dev_task_router.models import ModelLevel
from dev_task_router.profile_calibration import ProfileCalibrationRegistry
from dev_task_router.ui_fingerprint import UIFingerprint, UIFingerprintStore


def _fingerprint(automation_id: str = "effort-low") -> UIFingerprint:
    return UIFingerprint.from_rows(
        {
            "mode": [
                {
                    "name": "Low",
                    "control_type": "MenuItem",
                    "automation_id": automation_id,
                }
            ]
        },
        tracked_labels={"mode.effort.low": ("Low",)},
        platform="win32",
    )


def _result(*, verified: bool) -> SwitchResult:
    requested = RequestedProfile(
        surface="chat",
        level=ModelLevel.LOW,
        family="sol",
        effort="low",
        label="5.6 Sol Low",
    )
    return SwitchResult(
        requested=requested,
        actual_family="sol" if verified else None,
        actual_effort="low" if verified else None,
        verified=verified,
        backend="fake-windows-uia",
        changed=True,
        message="verified" if verified else "selector verification failed",
    )


class FakeController:
    def __init__(self, result: SwitchResult):
        self.result = result
        self.calls: list[tuple[ModelLevel, str]] = []

    def switch_level(self, level: ModelLevel, surface: str):
        self.calls.append((level, surface))
        return self.result


def test_live_calibration_records_only_verified_switch_on_matching_baseline(tmp_path) -> None:
    fingerprint = _fingerprint()
    UIFingerprintStore(tmp_path).save(fingerprint)
    controller = FakeController(_result(verified=True))

    current, record = LiveProfileCalibrator(
        tmp_path,
        fingerprint_supplier=lambda: fingerprint,
        switch_controller=controller,  # type: ignore[arg-type]
    ).calibrate(ModelLevel.LOW)

    assert current.digest == fingerprint.digest
    assert record.switch_verified is True
    assert record.end_to_end_verified is False
    assert controller.calls == [(ModelLevel.LOW, "chat")]
    coverage = ProfileCalibrationRegistry(tmp_path).coverage(fingerprint.digest)
    assert coverage.valid_levels == ("LOW",)


def test_live_calibration_refuses_missing_or_drifted_baseline_before_switch(tmp_path) -> None:
    current = _fingerprint()
    controller = FakeController(_result(verified=True))
    calibrator = LiveProfileCalibrator(
        tmp_path,
        fingerprint_supplier=lambda: current,
        switch_controller=controller,  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="no UI fingerprint baseline"):
        calibrator.calibrate(ModelLevel.LOW)
    assert controller.calls == []

    UIFingerprintStore(tmp_path).save(_fingerprint("old-control"))
    with pytest.raises(RuntimeError, match="differs"):
        calibrator.calibrate(ModelLevel.LOW)
    assert controller.calls == []


def test_live_calibration_refuses_unverified_switch(tmp_path) -> None:
    fingerprint = _fingerprint()
    UIFingerprintStore(tmp_path).save(fingerprint)
    controller = FakeController(_result(verified=False))

    with pytest.raises(RuntimeError, match="not verified"):
        LiveProfileCalibrator(
            tmp_path,
            fingerprint_supplier=lambda: fingerprint,
            switch_controller=controller,  # type: ignore[arg-type]
        ).calibrate(ModelLevel.LOW)

    assert not ProfileCalibrationRegistry(tmp_path).path.exists()
