from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import load_local_switch, load_surfaces
from .conversation_response_ui import load_local_response_config
from .conversation_ui import WindowsUIAConversationBackend, load_local_conversation_config
from .mode_switch import (
    ModeSwitchBackend,
    ModeSwitchController,
    RequestedProfile,
    SwitchResult,
    WindowsUIAModeSwitchBackend,
)
from .models import ModelLevel
from .profile_calibration import ProfileCalibrationRecord, ProfileCalibrationRegistry
from .ui_fingerprint import UIFingerprint, UIFingerprintStore


def tracked_selector_labels(root: Path) -> dict[str, tuple[str, ...]]:
    mode = load_local_switch(root)
    conversation = load_local_conversation_config(root)
    response = load_local_response_config(root)
    tracked: dict[str, tuple[str, ...]] = {
        "mode.selector": mode.selector_labels,
        "conversation.composer": conversation.composer_labels,
        "conversation.send": conversation.send_labels,
        "response.busy": response.busy_labels,
    }
    for prefix, mapping in (
        ("mode.family", mode.family_labels),
        ("mode.effort", mode.effort_labels),
        ("mode.verify", mode.verify_labels),
    ):
        for key, labels in mapping.items():
            tracked[f"{prefix}.{key}"] = labels
    return {key: labels for key, labels in tracked.items() if labels}


def capture_windows_ui_fingerprint(root: Path) -> UIFingerprint:
    root = root.resolve()
    switch_config = load_local_switch(root)
    conversation_config = load_local_conversation_config(root)
    mode_rows = WindowsUIAModeSwitchBackend(switch_config).probe()
    conversation_rows = WindowsUIAConversationBackend(root, conversation_config).probe()
    return UIFingerprint.from_rows(
        {"mode": mode_rows, "conversation": conversation_rows},
        tracked_labels=tracked_selector_labels(root),
    )


@dataclass(frozen=True, slots=True)
class UIExecutionGuardResult:
    allowed: bool
    status: str
    message: str
    baseline_digest: str | None = None
    current_digest: str | None = None


class UIFingerprintExecutionGuard:
    """Fail closed on a known UI baseline drift before clicking mode controls.

    An absent baseline preserves the pre-V1 behavior: execution may continue using the
    existing exact-switch verification. Once the user records a baseline, every real
    Windows dispatch is guarded against selector-structure drift.
    """

    def __init__(
        self,
        root: Path,
        *,
        fingerprint_supplier: Callable[[], UIFingerprint] | None = None,
    ):
        self.root = root.resolve()
        self.store = UIFingerprintStore(self.root)
        self.fingerprint_supplier = fingerprint_supplier

    def check(self) -> UIExecutionGuardResult:
        baseline = self.store.load()
        if baseline is None:
            return UIExecutionGuardResult(
                allowed=True,
                status="UNCALIBRATED",
                message="no UI fingerprint baseline exists; exact switch verification remains authoritative",
            )
        try:
            current = (
                self.fingerprint_supplier()
                if self.fingerprint_supplier is not None
                else capture_windows_ui_fingerprint(self.root)
            )
        except (OSError, RuntimeError, ValueError) as exc:
            return UIExecutionGuardResult(
                allowed=False,
                status="PROBE_FAILED",
                message=f"could not verify current UI fingerprint: {exc}",
                baseline_digest=baseline.digest,
            )
        comparison = self.store.compare(current)
        if comparison.drifted:
            return UIExecutionGuardResult(
                allowed=False,
                status="DRIFT",
                message="current UI fingerprint differs from the calibrated selector structure",
                baseline_digest=baseline.digest,
                current_digest=current.digest,
            )
        return UIExecutionGuardResult(
            allowed=True,
            status="MATCH",
            message="current UI fingerprint matches the calibrated selector structure",
            baseline_digest=baseline.digest,
            current_digest=current.digest,
        )


class GuardedModeSwitchBackend:
    """Run the fingerprint guard immediately before any real mode-switch click."""

    def __init__(self, backend: ModeSwitchBackend, guard: UIFingerprintExecutionGuard):
        self.backend = backend
        self.guard = guard
        self.name = f"guarded-{backend.name}"

    def probe(self) -> list[dict[str, str]]:
        return self.backend.probe()

    def switch(self, requested: RequestedProfile) -> SwitchResult:
        guard = self.guard.check()
        if not guard.allowed:
            return SwitchResult(
                requested=requested,
                actual_family=None,
                actual_effort=None,
                verified=False,
                backend=self.name,
                changed=False,
                message=f"UI_DRIFT/{guard.status}: {guard.message}",
            )
        return self.backend.switch(requested)


class LiveProfileCalibrator:
    """Record a profile only after a real exact switch on the calibrated UI build."""

    def __init__(
        self,
        root: Path,
        *,
        fingerprint_supplier: Callable[[], UIFingerprint] | None = None,
        switch_controller: ModeSwitchController | None = None,
        registry: ProfileCalibrationRegistry | None = None,
    ):
        self.root = root.resolve()
        self.fingerprint_supplier = fingerprint_supplier
        self.switch_controller = switch_controller
        self.registry = registry or ProfileCalibrationRegistry(self.root)

    def _fingerprint(self) -> UIFingerprint:
        if self.fingerprint_supplier is not None:
            return self.fingerprint_supplier()
        return capture_windows_ui_fingerprint(self.root)

    def _controller(self) -> ModeSwitchController:
        if self.switch_controller is not None:
            return self.switch_controller
        config = load_local_switch(self.root)
        if not config.enabled:
            raise RuntimeError("local exact mode switching is disabled")
        if config.backend != "windows-uia":
            raise RuntimeError("live profile calibration requires the windows-uia backend")
        return ModeSwitchController(
            load_surfaces(self.root),
            WindowsUIAModeSwitchBackend(config),
        )

    def calibrate(
        self,
        level: ModelLevel,
        *,
        surface: str = "chat",
    ) -> tuple[UIFingerprint, ProfileCalibrationRecord]:
        if level == ModelLevel.NONE:
            raise ValueError("NONE has no ChatGPT profile calibration")
        current = self._fingerprint()
        baseline = UIFingerprintStore(self.root).load()
        if baseline is None:
            raise RuntimeError(
                "no UI fingerprint baseline exists; probe and record the target Windows UI first"
            )
        if current.digest != baseline.digest:
            raise RuntimeError(
                "current UI fingerprint differs from the recorded baseline; revalidate selectors before profile calibration"
            )
        result = self._controller().switch_level(level, surface)
        if not result.verified:
            raise RuntimeError(f"exact profile switch was not verified: {result.message}")
        record = self.registry.record_verified_switch(
            result,
            ui_fingerprint=current.digest,
        )
        return current, record
