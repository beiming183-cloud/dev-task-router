from __future__ import annotations

from pathlib import Path

import pytest

from dev_task_router.config import (
    autodev_dir,
    load_local_switch,
    load_surfaces,
    write_default_files,
)
from dev_task_router.local_cli import main as local_main
from dev_task_router.mode_switch import (
    DryRunModeSwitchBackend,
    ModeSwitchController,
    RequestedProfile,
    SwitchResult,
)
from dev_task_router.models import ModelLevel


def test_init_writes_safe_disabled_local_switch_profile(tmp_path: Path) -> None:
    paths = write_default_files(tmp_path, "demo")
    assert autodev_dir(tmp_path) / "local-switch.yaml" in paths
    config = load_local_switch(tmp_path)
    assert config.enabled is False
    assert config.backend == "windows-uia"
    assert config.selector_labels == ()
    assert config.effort_labels == {}


def test_chat_high_resolves_to_sol_high_without_touching_ui(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    controller = ModeSwitchController(load_surfaces(tmp_path), DryRunModeSwitchBackend())
    profile = controller.requested_profile(ModelLevel.HIGH, "chat")
    assert profile.family == "sol"
    assert profile.effort == "high"
    result = controller.switch_level(ModelLevel.HIGH, "chat")
    assert result.backend == "dry-run"
    assert result.verified is False
    assert result.changed is False
    assert "sol/high" in result.message


def test_unresolved_codex_pool_is_not_guessed(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    controller = ModeSwitchController(load_surfaces(tmp_path), DryRunModeSwitchBackend())
    with pytest.raises(ValueError, match="unresolved"):
        controller.requested_profile(ModelLevel.HIGH, "codex")


def test_none_has_no_mode_switch(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    controller = ModeSwitchController(load_surfaces(tmp_path), DryRunModeSwitchBackend())
    with pytest.raises(ValueError, match="NONE"):
        controller.switch_level(ModelLevel.NONE, "chat")


class VerifiedBackend:
    name = "fake-verified"

    def probe(self) -> list[dict[str, str]]:
        return [{"name": "High", "control_type": "Button", "automation_id": "reasoning"}]

    def switch(self, requested: RequestedProfile) -> SwitchResult:
        return SwitchResult(
            requested=requested,
            actual_family=requested.family,
            actual_effort=requested.effort,
            verified=True,
            backend=self.name,
            changed=True,
            message="verified",
        )


def test_controller_preserves_requested_and_actual_profile(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    controller = ModeSwitchController(load_surfaces(tmp_path), VerifiedBackend())
    result = controller.switch_level(ModelLevel.MEDIUM, "chat")
    assert result.requested.family == "sol"
    assert result.requested.effort == "medium"
    assert result.actual_family == "sol"
    assert result.actual_effort == "medium"
    assert result.verified is True


def test_local_cli_dry_run_reports_route(tmp_path: Path, capsys) -> None:
    write_default_files(tmp_path, "demo")
    code = local_main(
        ["--root", str(tmp_path), "switch", "HIGH", "--surface", "chat", "--dry-run", "--json"]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert '"level": "HIGH"' in out
    assert '"family": "sol"' in out
    assert '"effort": "high"' in out
    assert '"verified": false' in out
