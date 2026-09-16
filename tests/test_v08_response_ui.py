from __future__ import annotations

from dataclasses import dataclass

import pytest

from dev_task_router.conversation_response_ui import (
    LocalResponseConfig,
    WindowsUIAResponseSnapshotSource,
)


@dataclass
class ElementInfo:
    control_type: str
    automation_id: str = ""


class FakeControl:
    def __init__(self, name: str, control_type: str, automation_id: str = "", value: str | None = None):
        self._name = name
        self._value = value
        self.element_info = ElementInfo(control_type, automation_id)

    def window_text(self) -> str:
        return self._name

    def get_value(self):
        return self._value


class FakeUI:
    def __init__(self, controls: list[FakeControl]):
        self.controls = controls

    def _controls(self):
        return self.controls

    @staticmethod
    def _name(control) -> str:
        return control.window_text()

    @staticmethod
    def _control_type(control) -> str:
        return control.element_info.control_type

    @staticmethod
    def _read_value(control):
        return control.get_value()


def _config(**response_overrides) -> LocalResponseConfig:
    response = {
        "enabled": True,
        "busy_labels": ["Stop generating"],
        "busy_control_types": ["Button"],
        "assistant_control_types": ["Text", "Document"],
        "assistant_automation_id_regex": r"assistant-message-\d+",
        "poll_interval_seconds": 0.5,
        "timeout_seconds": 30,
        "stable_polls": 2,
    }
    response.update(response_overrides)
    return LocalResponseConfig.from_dict({"response": response})


def test_response_config_requires_selector_when_enabled() -> None:
    with pytest.raises(ValueError, match="assistant_automation_id_regex"):
        LocalResponseConfig.from_dict({"response": {"enabled": True}})


def test_response_source_filters_chrome_and_reads_assistant_messages(tmp_path) -> None:
    ui = FakeUI(
        [
            FakeControl("ChatGPT", "Window", "root"),
            FakeControl("Stop generating", "Button", "stop"),
            FakeControl("navigation", "Text", "sidebar-1", "ignore me"),
            FakeControl("first answer", "Document", "assistant-message-1", "first answer"),
            FakeControl("second answer", "Text", "assistant-message-2", "second answer"),
        ]
    )
    source = WindowsUIAResponseSnapshotSource(tmp_path, _config(), ui)

    snapshot = source.snapshot()

    assert snapshot.busy is True
    assert snapshot.messages == ("first answer", "second answer")


def test_response_source_can_work_without_busy_selector(tmp_path) -> None:
    ui = FakeUI(
        [FakeControl("answer", "Document", "assistant-message-1", "answer")]
    )
    source = WindowsUIAResponseSnapshotSource(tmp_path, _config(busy_labels=[]), ui)

    snapshot = source.snapshot()

    assert snapshot.busy is False
    assert snapshot.messages == ("answer",)


def test_response_source_refuses_disabled_collection(tmp_path) -> None:
    config = _config(enabled=False)
    source = WindowsUIAResponseSnapshotSource(tmp_path, config, FakeUI([]))

    with pytest.raises(RuntimeError, match="response collection is disabled"):
        source.snapshot()
