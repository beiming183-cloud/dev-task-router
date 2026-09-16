from __future__ import annotations

import json

import yaml

from dev_task_router.config import autodev_dir, load_plan, write_default_files
from dev_task_router.loop_cli import main
from dev_task_router.state import StateStore


def _project(tmp_path) -> None:
    write_default_files(tmp_path, "demo")
    plan_data = {
        "version": 3,
        "project": "demo",
        "stages": [
            {
                "id": "stage",
                "steps": [
                    {
                        "id": "step",
                        "tasks": [
                            {
                                "id": "feature",
                                "title": "Implement bounded feature",
                                "kind": "normal_code",
                                "prompt": "Implement the bounded feature using the existing architecture.",
                                "acceptance": ["targeted unit test passes"],
                                "max_attempts": 2,
                                "escalate_after": 1,
                            }
                        ],
                    }
                ],
            }
        ],
    }
    (autodev_dir(tmp_path) / "plan.yaml").write_text(
        yaml.safe_dump(plan_data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    StateStore(tmp_path).create(load_plan(tmp_path))


def test_local_prepare_cli_is_inspection_only(tmp_path, capsys) -> None:
    _project(tmp_path)

    code = main(["--root", str(tmp_path), "prepare", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["task_id"] == "feature"
    assert payload["deterministic"] is False
    assert payload["requested_profile"]["surface"] == "chat"
    assert payload["requested_profile"]["family"] == "sol"
    assert payload["context_pack"]["task_id"] == "feature"
    assert StateStore(tmp_path).load()["tasks"]["feature"]["attempts"] == 0


def test_local_gate_dry_run_never_claims_verified_dispatch(tmp_path, capsys) -> None:
    _project(tmp_path)

    code = main(["--root", str(tmp_path), "gate", "--dry-run", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["allowed_to_dispatch"] is False
    assert payload["blocker"] == "MODE_SWITCH"
    assert payload["switch"]["backend"] == "dry-run"
    assert payload["switch"]["verified"] is False
    assert StateStore(tmp_path).load()["tasks"]["feature"]["attempts"] == 0
