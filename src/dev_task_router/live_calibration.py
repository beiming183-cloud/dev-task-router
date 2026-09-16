from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .config import load_local_switch, load_surfaces
from .conversation_response_ui import load_local_response_config
from .conversation_ui import WindowsUIAConversationBackend, load_local_conversation_config
from .mode_switch import ModeSwitchController, WindowsUIAModeSwitchBackend
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
