from __future__ import annotations

import json

import pytest

from dev_task_router.config import LOCAL_CONVERSATION_FILE, autodev_dir, write_default_files
from dev_task_router.conversation_ui import (
    DispatchLedger,
    LocalConversationConfig,
    WindowsUIAConversationBackend,
    load_local_conversation_config,
)
from dev_task_router.local_loop import LocalExecutionEnvelope
from dev_task_router.mode_switch import RequestedProfile
from dev_task_router.models import ModelLevel
from dev_task_router.rolling_context import TaskContextPack


class FakeControl:
    def __init__(self, name: str, control_type: str):
        self.value = name
        self.control_type = control_type
        self.invoked = 0

    def window_text(self):
        return self.value

    def get_value(self):
        return self.value

    def set_edit_text(self, text: str):
        self.value = text

    def invoke(self):
        self.invoked += 1

    @property
    def element_info(self):
        class Info:
            pass

        info = Info()
        info.control_type = self.control_type
        info.automation_id = ""
        return info


class CorruptComposer(FakeControl):
    def set_edit_text(self, text: str):
        self.value = text + " CORRUPTED"


class FakeConversationBackend(WindowsUIAConversationBackend):
    def __init__(self, root, config, composer=None):
        super().__init__(root, config)
        self.composer = composer or FakeControl("Message", "Edit")
        self.send = FakeControl("Send", "Button")

    def _controls(self):
        return [self.composer, self.send]


def _config(**overrides) -> LocalConversationConfig:
    data = {
        "enabled": True,
        "backend": "windows-uia",
        "window": {"title_regex": ".*ChatGPT.*"},
        "composer": {"labels": ["Message"], "control_types": ["Edit"]},
        "send": {"labels": ["Send"], "control_types": ["Button"]},
        "limits": {"max_prompt_chars": 60000},
    }
    data.update(overrides)
    return LocalConversationConfig.from_dict(data)


def _envelope() -> LocalExecutionEnvelope:
    pack = TaskContextPack(
        project="demo",
        stage="stage",
        step="step",
        task_id="task",
        task_title="Implement feature",
        goal="Finish the project in one canonical conversation.",
        decisions=("Keep SelectionState as source of truth",),
        constraints=("Do not break history",),
        stage_notes=(),
        task_notes=(),
        acceptance=("targeted tests pass",),
        failures=(),
        repository=None,
        requested_route={"level": "MEDIUM", "family": "sol", "effort": "medium"},
        next_action="Implement the feature.",
        stale_context=False,
        omitted={},
    )
    profile = RequestedProfile(
        surface="chat",
        level=ModelLevel.MEDIUM,
        family="sol",
        effort="medium",
        label="5.6 Sol Medium",
    )
    return LocalExecutionEnvelope(
        task_id="task",
        stage="stage",
        step="step",
        difficulty=ModelLevel.MEDIUM,
        context_pack=pack,
        requested_profile=profile,
        deterministic=False,
    )


def test_default_local_conversation_config_is_disabled(tmp_path) -> None:
    paths = write_default_files(tmp_path, "demo")
    config = load_local_conversation_config(tmp_path)

    assert any(path.name == LOCAL_CONVERSATION_FILE for path in paths)
    assert config.enabled is False
    assert config.composer_labels == ()
    assert config.send_labels == ()


def test_conversation_config_rejects_bad_limits() -> None:
    with pytest.raises(ValueError, match="max_prompt_chars"):
        LocalConversationConfig.from_dict(
            {
                "enabled": False,
                "backend": "windows-uia",
                "window": {},
                "composer": {},
                "send": {},
                "limits": {"max_prompt_chars": 0},
            }
        )


def test_sender_verifies_full_prompt_before_click_and_records_submission(tmp_path) -> None:
    envelope = _envelope()
    backend = FakeConversationBackend(tmp_path, _config())

    result = backend.dispatch(envelope)
    dispatch_id = backend.dispatch_id(envelope)
    ledger = DispatchLedger(tmp_path).get(dispatch_id)

    assert result.accepted is True
    assert backend.composer.value == envelope.prompt_text()
    assert backend.send.invoked == 1
    assert ledger is not None and ledger["status"] == "submitted"
    assert dispatch_id in result.message


def test_duplicate_dispatch_is_blocked_before_second_send(tmp_path) -> None:
    envelope = _envelope()
    backend = FakeConversationBackend(tmp_path, _config())
    backend.dispatch(envelope)

    with pytest.raises(RuntimeError, match="duplicate dispatch blocked"):
        backend.dispatch(envelope)

    assert backend.send.invoked == 1


def test_readback_mismatch_fails_before_ledger_reservation_or_send(tmp_path) -> None:
    envelope = _envelope()
    backend = FakeConversationBackend(
        tmp_path,
        _config(),
        composer=CorruptComposer("Message", "Edit"),
    )

    with pytest.raises(RuntimeError, match="read-back"):
        backend.dispatch(envelope)

    dispatch_id = backend.dispatch_id(envelope)
    assert DispatchLedger(tmp_path).get(dispatch_id) is None
    assert backend.send.invoked == 0


def test_disabled_sender_fails_closed(tmp_path) -> None:
    envelope = _envelope()
    config = LocalConversationConfig.from_dict(
        {
            "enabled": False,
            "backend": "windows-uia",
            "window": {"title_regex": ".*ChatGPT.*"},
            "composer": {"labels": ["Message"], "control_types": ["Edit"]},
            "send": {"labels": ["Send"], "control_types": ["Button"]},
            "limits": {"max_prompt_chars": 60000},
        }
    )
    backend = FakeConversationBackend(tmp_path, config)

    with pytest.raises(RuntimeError, match="disabled"):
        backend.dispatch(envelope)

    assert backend.send.invoked == 0


def test_dispatch_ledger_submitting_state_is_sticky(tmp_path) -> None:
    ledger = DispatchLedger(tmp_path)
    ledger.reserve("abc", "task")

    with pytest.raises(RuntimeError, match="duplicate dispatch blocked"):
        ledger.reserve("abc", "task")

    payload = json.loads((autodev_dir(tmp_path) / "local-dispatch.json").read_text(encoding="utf-8"))
    assert payload["entries"]["abc"]["status"] == "submitting"
