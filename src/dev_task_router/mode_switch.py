from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any, Protocol

from .models import ModelLevel
from .surface import SurfaceCatalog, SurfaceDecision, SurfaceModel


@dataclass(frozen=True, slots=True)
class RequestedProfile:
    surface: str
    level: ModelLevel
    family: str
    effort: str | None
    label: str | None = None

    @classmethod
    def from_surface_decision(cls, decision: SurfaceDecision) -> "RequestedProfile":
        if not decision.resolved or decision.model is None:
            raise ValueError(
                f"surface route is unresolved for {decision.surface}/{decision.level.value}"
            )
        return cls(
            surface=decision.surface,
            level=decision.level,
            family=decision.model.family,
            effort=decision.model.effort,
            label=decision.model.label,
        )


@dataclass(frozen=True, slots=True)
class SwitchResult:
    requested: RequestedProfile
    actual_family: str | None
    actual_effort: str | None
    verified: bool
    backend: str
    changed: bool
    message: str


@dataclass(frozen=True, slots=True)
class LocalSwitchConfig:
    enabled: bool
    backend: str
    window_title_regex: str
    selector_labels: tuple[str, ...]
    family_labels: dict[str, tuple[str, ...]]
    effort_labels: dict[str, tuple[str, ...]]
    verify_labels: dict[str, tuple[str, ...]]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocalSwitchConfig":
        if not isinstance(data, dict):
            raise ValueError("local switch config must be a mapping")
        backend = str(data.get("backend", "windows-uia")).strip().lower()
        if backend not in {"windows-uia", "dry-run"}:
            raise ValueError("local switch backend must be windows-uia or dry-run")

        window = data.get("window", {})
        selector = data.get("selector", {})
        if not isinstance(window, dict) or not isinstance(selector, dict):
            raise ValueError("local switch window/selector must be mappings")

        title_regex = str(window.get("title_regex", ".*ChatGPT.*")).strip()
        try:
            re.compile(title_regex)
        except re.error as exc:
            raise ValueError(f"invalid window title_regex: {exc}") from exc

        def _string_tuple(value: Any, name: str) -> tuple[str, ...]:
            if value is None:
                return ()
            if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
                raise ValueError(f"local switch {name} must be a string list")
            return tuple(x.strip() for x in value if x.strip())

        def _label_map(value: Any, name: str) -> dict[str, tuple[str, ...]]:
            if value is None:
                return {}
            if not isinstance(value, dict):
                raise ValueError(f"local switch {name} must be a mapping")
            result: dict[str, tuple[str, ...]] = {}
            for raw_key, raw_labels in value.items():
                key = str(raw_key).strip().lower()
                labels = _string_tuple(raw_labels, f"{name}.{key}")
                if labels:
                    result[key] = labels
            return result

        return cls(
            enabled=bool(data.get("enabled", False)),
            backend=backend,
            window_title_regex=title_regex,
            selector_labels=_string_tuple(selector.get("open_labels"), "selector.open_labels"),
            family_labels=_label_map(data.get("family_labels"), "family_labels"),
            effort_labels=_label_map(data.get("effort_labels"), "effort_labels"),
            verify_labels=_label_map(data.get("verify_labels"), "verify_labels"),
        )


class ModeSwitchBackend(Protocol):
    name: str

    def probe(self) -> list[dict[str, str]]: ...

    def switch(self, requested: RequestedProfile) -> SwitchResult: ...


class DryRunModeSwitchBackend:
    name = "dry-run"

    def probe(self) -> list[dict[str, str]]:
        return []

    def switch(self, requested: RequestedProfile) -> SwitchResult:
        return SwitchResult(
            requested=requested,
            actual_family=None,
            actual_effort=None,
            verified=False,
            backend=self.name,
            changed=False,
            message=(
                f"dry-run only: would request {requested.surface} "
                f"{requested.family}/{requested.effort or 'default'}"
            ),
        )


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _matches(text: str, labels: tuple[str, ...]) -> bool:
    value = _norm(text)
    return any(_norm(label) == value or _norm(label) in value for label in labels)


class WindowsUIAModeSwitchBackend:
    """Config-driven Windows UI Automation backend.

    It deliberately avoids screen coordinates. A one-time `mode probe` is used to
    discover stable accessibility labels for the user's current ChatGPT build.
    """

    name = "windows-uia"

    def __init__(self, config: LocalSwitchConfig):
        self.config = config

    @staticmethod
    def _desktop():
        if sys.platform != "win32":
            raise RuntimeError("windows-uia backend requires Windows")
        try:
            from pywinauto import Desktop
        except ImportError as exc:
            raise RuntimeError(
                "windows-uia backend requires the local extra: pip install -e '.[local]'"
            ) from exc
        return Desktop(backend="uia")

    def _window(self):
        desktop = self._desktop()
        windows = desktop.windows(title_re=self.config.window_title_regex, visible_only=True)
        if not windows:
            raise RuntimeError(
                f"no visible window matches {self.config.window_title_regex!r}; open ChatGPT first"
            )
        return windows[0]

    @staticmethod
    def _control_name(control) -> str:
        try:
            return (control.window_text() or "").strip()
        except Exception:
            return ""

    def _controls(self) -> list:
        window = self._window()
        return [window, *window.descendants()]

    def probe(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for control in self._controls():
            name = self._control_name(control)
            if not name:
                continue
            try:
                control_type = str(control.element_info.control_type or "")
                automation_id = str(control.element_info.automation_id or "")
            except Exception:
                control_type = ""
                automation_id = ""
            rows.append(
                {
                    "name": name,
                    "control_type": control_type,
                    "automation_id": automation_id,
                }
            )
        # Keep probe useful and deterministic without dumping duplicate text.
        unique: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            key = (row["name"], row["control_type"], row["automation_id"])
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique

    def _find(self, labels: tuple[str, ...], *, controls: list | None = None):
        if not labels:
            return None
        for control in controls or self._controls():
            if _matches(self._control_name(control), labels):
                return control
        return None

    @staticmethod
    def _click(control) -> None:
        try:
            control.invoke()
            return
        except Exception:
            pass
        try:
            control.click_input()
            return
        except Exception as exc:
            raise RuntimeError("matched UI control could not be invoked") from exc

    def _verification_labels(self, requested: RequestedProfile) -> tuple[str, ...]:
        effort = (requested.effort or "").lower()
        explicit = self.config.verify_labels.get(effort, ())
        if explicit:
            return explicit
        return self.config.effort_labels.get(effort, ())

    def _verify(self, requested: RequestedProfile) -> bool:
        labels = self._verification_labels(requested)
        if not labels:
            return False
        return self._find(labels) is not None

    def switch(self, requested: RequestedProfile) -> SwitchResult:
        if not self.config.enabled:
            raise RuntimeError(
                "local exact switching is disabled; run `autodev mode probe` and calibrate "
                ".autodev/local-switch.yaml first"
            )
        if not self.config.selector_labels:
            raise RuntimeError("selector.open_labels is empty; run mode probe and calibrate it")

        effort = (requested.effort or "").lower()
        target_effort = self.config.effort_labels.get(effort, ())
        if requested.effort and not target_effort:
            raise RuntimeError(f"no UI labels configured for effort {requested.effort!r}")

        family = requested.family.lower()
        target_family = self.config.family_labels.get(family, ())

        # If the selected profile is already visible, do not click anything.
        if self._verify(requested):
            return SwitchResult(
                requested=requested,
                actual_family=requested.family,
                actual_effort=requested.effort,
                verified=True,
                backend=self.name,
                changed=False,
                message="requested profile is already visible in the current ChatGPT UI",
            )

        selector = self._find(self.config.selector_labels)
        if selector is None:
            raise RuntimeError("configured model/reasoning selector was not found")
        self._click(selector)

        controls = self._controls()
        if target_family:
            family_control = self._find(target_family, controls=controls)
            if family_control is None:
                raise RuntimeError(f"configured family labels not found for {requested.family!r}")
            self._click(family_control)
            controls = self._controls()

        if target_effort:
            effort_control = self._find(target_effort, controls=controls)
            if effort_control is None:
                raise RuntimeError(f"configured effort labels not found for {requested.effort!r}")
            self._click(effort_control)

        verified = self._verify(requested)
        return SwitchResult(
            requested=requested,
            actual_family=requested.family if verified else None,
            actual_effort=requested.effort if verified else None,
            verified=verified,
            backend=self.name,
            changed=True,
            message=(
                "exact local switch verified"
                if verified
                else "UI actions completed but the requested profile could not be verified"
            ),
        )


class ModeSwitchController:
    def __init__(
        self,
        surfaces: SurfaceCatalog,
        backend: ModeSwitchBackend,
    ):
        self.surfaces = surfaces
        self.backend = backend

    def requested_profile(self, level: ModelLevel, surface: str = "chat") -> RequestedProfile:
        return RequestedProfile.from_surface_decision(self.surfaces.route(level, surface))

    def switch_level(self, level: ModelLevel, surface: str = "chat") -> SwitchResult:
        if level == ModelLevel.NONE:
            raise ValueError("NONE is deterministic and has no ChatGPT mode to switch")
        return self.backend.switch(self.requested_profile(level, surface))
