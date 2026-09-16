from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .config import LOCAL_CONVERSATION_FILE, load_local_conversation_dict
from .conversation_ui import (
    LocalConversationConfig,
    WindowsUIAConversationBackend,
    _matches,
    _norm,
)
from .response_monitor import ResponseSnapshot


@dataclass(frozen=True, slots=True)
class LocalResponseConfig:
    enabled: bool
    busy_labels: tuple[str, ...]
    busy_control_types: tuple[str, ...]
    assistant_control_types: tuple[str, ...]
    assistant_automation_id_regex: str
    poll_interval_seconds: float
    timeout_seconds: float
    stable_polls: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocalResponseConfig":
        if not isinstance(data, dict):
            raise ValueError("local conversation config must be a mapping")
        response = data.get("response", {})
        if not isinstance(response, dict):
            raise ValueError("local conversation response must be a mapping")

        def strings(value: Any, name: str) -> tuple[str, ...]:
            if value is None:
                return ()
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"local conversation {name} must be a string list")
            return tuple(item.strip() for item in value if item.strip())

        automation_regex = str(response.get("assistant_automation_id_regex", "")).strip()
        if automation_regex:
            try:
                re.compile(automation_regex)
            except re.error as exc:
                raise ValueError(f"invalid assistant_automation_id_regex: {exc}") from exc

        poll = float(response.get("poll_interval_seconds", 1.0))
        timeout = float(response.get("timeout_seconds", 900.0))
        stable = int(response.get("stable_polls", 2))
        if poll <= 0:
            raise ValueError("response poll_interval_seconds must be > 0")
        if timeout <= 0:
            raise ValueError("response timeout_seconds must be > 0")
        if stable < 1:
            raise ValueError("response stable_polls must be >= 1")

        enabled = bool(response.get("enabled", False))
        if enabled and not automation_regex:
            raise ValueError(
                "response collection is enabled but assistant_automation_id_regex is empty"
            )

        return cls(
            enabled=enabled,
            busy_labels=strings(response.get("busy_labels"), "response.busy_labels"),
            busy_control_types=strings(
                response.get("busy_control_types", ["Button"]),
                "response.busy_control_types",
            ),
            assistant_control_types=strings(
                response.get("assistant_control_types", ["Text", "Document"]),
                "response.assistant_control_types",
            ),
            assistant_automation_id_regex=automation_regex,
            poll_interval_seconds=poll,
            timeout_seconds=timeout,
            stable_polls=stable,
        )


def load_local_response_config(root: Path) -> LocalResponseConfig:
    return LocalResponseConfig.from_dict(load_local_conversation_dict(root))


class UIControlSource(Protocol):
    def _controls(self) -> list: ...

    @staticmethod
    def _name(control) -> str: ...

    @staticmethod
    def _control_type(control) -> str: ...

    @staticmethod
    def _read_value(control) -> str | None: ...


class WindowsUIAResponseSnapshotSource:
    """Read generation state and assistant messages from calibrated UIA controls.

    The source is intentionally strict about assistant-message identification. An
    empty automation-id regex is never interpreted as "match everything" because
    that could mistake unrelated ChatGPT chrome for model output.
    """

    def __init__(
        self,
        root: Path,
        response_config: LocalResponseConfig | None = None,
        ui_backend: UIControlSource | None = None,
    ):
        self.root = root
        self.config = response_config or load_local_response_config(root)
        if ui_backend is None:
            conversation_config = LocalConversationConfig.from_dict(
                load_local_conversation_dict(root)
            )
            ui_backend = WindowsUIAConversationBackend(root, conversation_config)
        self.ui = ui_backend

    @staticmethod
    def _automation_id(control) -> str:
        try:
            return str(control.element_info.automation_id or "")
        except Exception:
            return ""

    def _busy(self, controls: list) -> bool:
        if not self.config.busy_labels:
            return False
        allowed = {_norm(item) for item in self.config.busy_control_types}
        for control in controls:
            if allowed and _norm(self.ui._control_type(control)) not in allowed:
                continue
            if _matches(self.ui._name(control), self.config.busy_labels):
                return True
        return False

    def _assistant_messages(self, controls: list) -> tuple[str, ...]:
        pattern_text = self.config.assistant_automation_id_regex
        if not pattern_text:
            raise RuntimeError(
                f"response collection is uncalibrated; set assistant_automation_id_regex in {LOCAL_CONVERSATION_FILE}"
            )
        pattern = re.compile(pattern_text)
        allowed = {_norm(item) for item in self.config.assistant_control_types}
        messages: list[str] = []
        for control in controls:
            if allowed and _norm(self.ui._control_type(control)) not in allowed:
                continue
            if not pattern.search(self._automation_id(control)):
                continue
            text = self.ui._read_value(control)
            if text is None or not text.strip():
                text = self.ui._name(control)
            text = (text or "").strip()
            if text:
                messages.append(text)
        return tuple(messages)

    def snapshot(self) -> ResponseSnapshot:
        if not self.config.enabled:
            raise RuntimeError(
                f"response collection is disabled; calibrate {LOCAL_CONVERSATION_FILE} first"
            )
        controls = self.ui._controls()
        return ResponseSnapshot(
            busy=self._busy(controls),
            messages=self._assistant_messages(controls),
        )
