from __future__ import annotations

import pytest

from dev_task_router.mode_switch import RequestedProfile, SwitchResult
from dev_task_router.models import ModelLevel
from dev_task_router.profile_calibration import ProfileCalibrationRegistry


def _switch(level: ModelLevel, effort: str, *, verified: bool = True) -> SwitchResult:
    requested = RequestedProfile(
        surface="chat",
        level=level,
        family="sol",
        effort=effort,
        label=f"5.6 Sol {effort.title()}",
    )
    return SwitchResult(
        requested=requested,
        actual_family="sol" if verified else None,
        actual_effort=effort if verified else None,
        verified=verified,
        backend="fake-windows-uia",
        changed=True,
        message="verified" if verified else "not verified",
    )


def test_profile_calibration_requires_real_verified_switch_and_current_fingerprint(tmp_path) -> None:
    registry = ProfileCalibrationRegistry(tmp_path)
    initial = registry.coverage("ui-v1")
    assert initial.missing_levels == ("LOW", "MEDIUM", "HIGH")
    assert initial.switch_complete is False

    with pytest.raises(ValueError, match="unverified"):
        registry.record_verified_switch(
            _switch(ModelLevel.LOW, "low", verified=False),
            ui_fingerprint="ui-v1",
        )

    registry.record_verified_switch(_switch(ModelLevel.LOW, "low"), ui_fingerprint="ui-v1")
    registry.record_verified_switch(
        _switch(ModelLevel.MEDIUM, "medium"), ui_fingerprint="ui-v1"
    )
    registry.record_verified_switch(_switch(ModelLevel.HIGH, "high"), ui_fingerprint="ui-v1")

    current = registry.coverage("ui-v1")
    assert current.valid_levels == ("LOW", "MEDIUM", "HIGH")
    assert current.switch_complete is True
    assert current.end_to_end_complete is False

    stale = registry.coverage("ui-v2")
    assert stale.stale_levels == ("LOW", "MEDIUM", "HIGH")
    assert stale.switch_complete is False


def test_end_to_end_calibration_is_separate_from_switch_verification(tmp_path) -> None:
    registry = ProfileCalibrationRegistry(tmp_path)
    for level, effort in (
        (ModelLevel.LOW, "low"),
        (ModelLevel.MEDIUM, "medium"),
        (ModelLevel.HIGH, "high"),
    ):
        registry.record_verified_switch(_switch(level, effort), ui_fingerprint="ui-v1")

    registry.mark_end_to_end_verified(
        ModelLevel.LOW,
        ui_fingerprint="ui-v1",
        dispatch_id="dispatch-low",
    )
    coverage = registry.coverage("ui-v1")
    assert coverage.e2e_levels == ("LOW",)
    assert coverage.end_to_end_complete is False

    with pytest.raises(ValueError, match="stale"):
        registry.mark_end_to_end_verified(
            ModelLevel.MEDIUM,
            ui_fingerprint="ui-v2",
            dispatch_id="dispatch-medium",
        )

    registry.mark_end_to_end_verified(
        ModelLevel.MEDIUM,
        ui_fingerprint="ui-v1",
        dispatch_id="dispatch-medium",
    )
    registry.mark_end_to_end_verified(
        ModelLevel.HIGH,
        ui_fingerprint="ui-v1",
        dispatch_id="dispatch-high",
    )
    complete = registry.coverage("ui-v1")
    assert complete.end_to_end_complete is True
    assert complete.e2e_levels == ("LOW", "MEDIUM", "HIGH")
