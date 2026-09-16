from __future__ import annotations

from dev_task_router.live_calibration import (
    GuardedModeSwitchBackend,
    UIFingerprintExecutionGuard,
)
from dev_task_router.mode_switch import RequestedProfile, SwitchResult
from dev_task_router.models import ModelLevel
from dev_task_router.ui_fingerprint import UIFingerprint, UIFingerprintStore


def _fingerprint(automation_id: str) -> UIFingerprint:
    return UIFingerprint.from_rows(
        {
            "mode": [
                {
                    "name": "High",
                    "control_type": "MenuItem",
                    "automation_id": automation_id,
                }
            ]
        },
        tracked_labels={"mode.effort.high": ("High",)},
        platform="win32",
    )


class FakeBackend:
    name = "fake"

    def __init__(self):
        self.switch_calls = 0

    def probe(self):
        return []

    def switch(self, requested: RequestedProfile) -> SwitchResult:
        self.switch_calls += 1
        return SwitchResult(
            requested=requested,
            actual_family=requested.family,
            actual_effort=requested.effort,
            verified=True,
            backend=self.name,
            changed=True,
            message="verified",
        )


def _requested() -> RequestedProfile:
    return RequestedProfile(
        surface="chat",
        level=ModelLevel.HIGH,
        family="sol",
        effort="high",
        label="5.6 Sol High",
    )


def test_guard_preserves_existing_exact_verification_when_no_baseline_exists(tmp_path) -> None:
    backend = FakeBackend()
    guard = UIFingerprintExecutionGuard(
        tmp_path,
        fingerprint_supplier=lambda: _fingerprint("current"),
    )
    result = GuardedModeSwitchBackend(backend, guard).switch(_requested())

    assert result.verified is True
    assert backend.switch_calls == 1


def test_guard_blocks_before_mode_click_when_calibrated_ui_drifted(tmp_path) -> None:
    UIFingerprintStore(tmp_path).save(_fingerprint("baseline"))
    backend = FakeBackend()
    guard = UIFingerprintExecutionGuard(
        tmp_path,
        fingerprint_supplier=lambda: _fingerprint("changed"),
    )

    result = GuardedModeSwitchBackend(backend, guard).switch(_requested())

    assert result.verified is False
    assert result.changed is False
    assert result.actual_family is None
    assert "UI_DRIFT/DRIFT" in result.message
    assert backend.switch_calls == 0


def test_guard_allows_mode_click_when_calibrated_ui_matches(tmp_path) -> None:
    fingerprint = _fingerprint("stable")
    UIFingerprintStore(tmp_path).save(fingerprint)
    backend = FakeBackend()
    guard = UIFingerprintExecutionGuard(
        tmp_path,
        fingerprint_supplier=lambda: fingerprint,
    )

    result = GuardedModeSwitchBackend(backend, guard).switch(_requested())

    assert result.verified is True
    assert backend.switch_calls == 1
