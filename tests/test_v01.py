from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from dev_task_router.cli import main
from dev_task_router.config import autodev_dir, load_plan, write_default_files
from dev_task_router.models import WorkflowStatus
from dev_task_router.state import StateStore
from dev_task_router.workflow import WorkflowEngine


def test_init_creates_minimal_project(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path), "init", "--name", "demo"]) == 0
    assert (tmp_path / ".autodev" / "project.yaml").exists()
    assert (tmp_path / ".autodev" / "plan.yaml").exists()
    state = json.loads((tmp_path / ".autodev" / "state.json").read_text(encoding="utf-8"))
    assert state["project"] == "demo"
    assert state["status"] == "READY"


def test_workflow_runs_tasks_and_checks(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    plan_path = autodev_dir(tmp_path) / "plan.yaml"
    plan_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project": "demo",
                "tasks": [
                    {
                        "id": "write-marker",
                        "title": "write marker",
                        "model": "NONE",
                        "command": [
                            sys.executable,
                            "-c",
                            "from pathlib import Path; Path('marker.txt').write_text('ok', encoding='utf-8')",
                        ],
                        "checks": [
                            [
                                sys.executable,
                                "-c",
                                "from pathlib import Path; assert Path('marker.txt').read_text(encoding='utf-8') == 'ok'",
                            ]
                        ],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    plan = load_plan(tmp_path)
    state = WorkflowEngine(tmp_path, plan, StateStore(tmp_path)).run()
    assert state["status"] == WorkflowStatus.PASSED.value
    assert (tmp_path / "marker.txt").read_text(encoding="utf-8") == "ok"
    assert state["tasks"]["write-marker"]["status"] == "PASSED"


def test_failure_is_persisted(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    plan_path = autodev_dir(tmp_path) / "plan.yaml"
    plan_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project": "demo",
                "tasks": [
                    {
                        "id": "fail",
                        "title": "fail task",
                        "model": "NONE",
                        "command": [sys.executable, "-c", "raise SystemExit(7)"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    plan = load_plan(tmp_path)
    state = WorkflowEngine(tmp_path, plan, StateStore(tmp_path)).run()
    assert state["status"] == WorkflowStatus.FAILED.value
    assert state["current_task"] == "fail"
    assert state["tasks"]["fail"]["attempts"] == 1
    assert state["tasks"]["fail"]["status"] == "FAILED"


def test_pause_and_resume(tmp_path: Path) -> None:
    assert main(["--root", str(tmp_path), "init", "--name", "demo"]) == 0
    assert main(["--root", str(tmp_path), "pause"]) == 0
    state = StateStore(tmp_path).load()
    assert state["status"] == "PAUSED"
    assert main(["--root", str(tmp_path), "resume"]) == 0
    state = StateStore(tmp_path).load()
    assert state["status"] == "PASSED"


def test_missing_command_becomes_failed_state(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    plan_path = autodev_dir(tmp_path) / "plan.yaml"
    plan_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project": "demo",
                "tasks": [
                    {
                        "id": "missing",
                        "title": "missing command",
                        "model": "NONE",
                        "command": ["__autodev_command_that_does_not_exist__"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    plan = load_plan(tmp_path)
    state = WorkflowEngine(tmp_path, plan, StateStore(tmp_path)).run()
    assert state["status"] == WorkflowStatus.FAILED.value
    assert state["tasks"]["missing"]["status"] == "FAILED"
    assert state["tasks"]["missing"]["last_error"]


def test_failed_workflow_is_not_retried_by_start(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    plan_path = autodev_dir(tmp_path) / "plan.yaml"
    plan_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project": "demo",
                "tasks": [
                    {
                        "id": "fail-once",
                        "title": "fail once",
                        "model": "NONE",
                        "command": [sys.executable, "-c", "raise SystemExit(3)"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    plan = load_plan(tmp_path)
    store = StateStore(tmp_path)
    first = WorkflowEngine(tmp_path, plan, store).run()
    assert first["tasks"]["fail-once"]["attempts"] == 1
    assert main(["--root", str(tmp_path), "start"]) == 1
    second = store.load()
    assert second["tasks"]["fail-once"]["attempts"] == 1
