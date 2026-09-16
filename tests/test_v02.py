from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from dev_task_router.cli import main
from dev_task_router.config import autodev_dir, load_models, load_plan, write_default_files
from dev_task_router.models import ModelLevel, TaskRole, WorkflowStatus
from dev_task_router.router import RuleRouter
from dev_task_router.state import StateStore
from dev_task_router.workflow import WorkflowEngine


def write_plan(root: Path, data: dict) -> None:
    (autodev_dir(root) / "plan.yaml").write_text(
        yaml.safe_dump(data, sort_keys=False), encoding="utf-8"
    )


def test_nested_plan_flattens_hierarchy_and_routes(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    write_plan(
        tmp_path,
        {
            "version": 2,
            "project": "demo",
            "stages": [
                {
                    "id": "design",
                    "title": "Design",
                    "steps": [
                        {
                            "id": "arch",
                            "title": "Architecture",
                            "tasks": [
                                {
                                    "id": "plan",
                                    "title": "Plan",
                                    "kind": "architecture",
                                    "role": "PLANNER",
                                    "command": [sys.executable, "-c", "pass"],
                                },
                                {
                                    "id": "test",
                                    "title": "Test",
                                    "kind": "test",
                                    "command": [sys.executable, "-c", "pass"],
                                },
                            ],
                        }
                    ],
                }
            ],
        },
    )
    plan = load_plan(tmp_path)
    assert [t.id for t in plan.tasks] == ["plan", "test"]
    assert plan.tasks[0].stage_id == "design"
    assert plan.tasks[0].step_id == "arch"
    assert plan.tasks[0].role == TaskRole.PLANNER
    router = RuleRouter(load_models(tmp_path))
    assert router.route(plan.tasks[0]).level == ModelLevel.HIGH
    assert router.route(plan.tasks[1]).level == ModelLevel.NONE


def test_explicit_level_overrides_rule(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    write_plan(
        tmp_path,
        {
            "version": 1,
            "project": "demo",
            "tasks": [
                {
                    "id": "doc",
                    "title": "Doc",
                    "kind": "docs",
                    "level": "HIGH",
                    "command": [sys.executable, "-c", "pass"],
                }
            ],
        },
    )
    task = load_plan(tmp_path).tasks[0]
    decision = RuleRouter(load_models(tmp_path)).route(task)
    assert decision.level == ModelLevel.HIGH
    assert decision.reason == "explicit task level"


def test_state_records_route_usage_and_handoff(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    write_plan(
        tmp_path,
        {
            "version": 2,
            "project": "demo",
            "stages": [
                {
                    "id": "impl",
                    "steps": [
                        {
                            "id": "code",
                            "tasks": [
                                {
                                    "id": "work",
                                    "title": "Work",
                                    "kind": "simple_edit",
                                    "command": [sys.executable, "-c", "print('ok')"],
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    )
    plan = load_plan(tmp_path)
    state = WorkflowEngine(tmp_path, plan, StateStore(tmp_path)).run()
    assert state["status"] == WorkflowStatus.PASSED.value
    route = state["tasks"]["work"]["route"]
    assert route["level"] == "LOW"
    assert route["model"] == "low"
    assert route["executor"] == "command"
    usage = (
        (autodev_dir(tmp_path) / "usage.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    assert len(usage) == 1
    record = json.loads(usage[0])
    assert record["task_id"] == "work" and record["status"] == "PASSED"
    handoff = (autodev_dir(tmp_path) / "handoff.md").read_text(encoding="utf-8")
    assert "impl" in handoff and "work" in handoff and "LOW" in handoff


def test_unknown_executor_fails_cleanly(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    models_path = autodev_dir(tmp_path) / "models.yaml"
    data = yaml.safe_load(models_path.read_text(encoding="utf-8"))
    data["profiles"]["HIGH"]["executor"] = "missing"
    models_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    write_plan(
        tmp_path,
        {
            "version": 1,
            "project": "demo",
            "tasks": [
                {
                    "id": "arch",
                    "title": "Arch",
                    "kind": "architecture",
                    "command": [sys.executable, "-c", "pass"],
                }
            ],
        },
    )
    plan = load_plan(tmp_path)
    state = WorkflowEngine(tmp_path, plan, StateStore(tmp_path)).run()
    assert state["status"] == "FAILED"
    assert "executor not registered" in state["tasks"]["arch"]["last_error"]


def test_legacy_v1_plan_is_supported(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    write_plan(
        tmp_path,
        {
            "version": 1,
            "project": "demo",
            "tasks": [
                {
                    "id": "legacy",
                    "title": "Legacy",
                    "model": "NONE",
                    "command": [sys.executable, "-c", "pass"],
                }
            ],
        },
    )
    plan = load_plan(tmp_path)
    assert plan.tasks[0].stage_id == "default"
    assert plan.tasks[0].step_id == "default"
    assert RuleRouter(load_models(tmp_path)).route(plan.tasks[0]).level == ModelLevel.NONE


def test_cli_init_creates_models_and_handoff_and_plan_shows_route(
    tmp_path: Path, capsys
) -> None:
    assert main(["--root", str(tmp_path), "init", "--name", "demo"]) == 0
    assert (autodev_dir(tmp_path) / "models.yaml").exists()
    assert (autodev_dir(tmp_path) / "handoff.md").exists()
    assert main(["--root", str(tmp_path), "plan"]) == 0
    out = capsys.readouterr().out
    assert "EXECUTOR/NONE" in out
    assert "local:none via command" in out


def test_agent_cli_executor_uses_routed_model_and_prompt(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    models_path = autodev_dir(tmp_path) / "models.yaml"
    data = yaml.safe_load(models_path.read_text(encoding="utf-8"))
    data["profiles"]["LOW"] = {
        "provider": "fake",
        "model": "tiny-model",
        "executor": "agent-cli",
        "command": [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path; Path('agent.txt').write_text(sys.argv[1]+'|'+sys.argv[2], encoding='utf-8')",
            "{model}",
            "{prompt}",
        ],
    }
    models_path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    write_plan(
        tmp_path,
        {
            "version": 2,
            "project": "demo",
            "stages": [
                {
                    "id": "s",
                    "steps": [
                        {
                            "id": "p",
                            "tasks": [
                                {
                                    "id": "agent",
                                    "title": "Agent",
                                    "kind": "simple_edit",
                                    "prompt": "change one thing",
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    )
    plan = load_plan(tmp_path)
    state = WorkflowEngine(tmp_path, plan, StateStore(tmp_path)).run()
    assert state["status"] == "PASSED"
    assert (tmp_path / "agent.txt").read_text(encoding="utf-8") == "tiny-model|change one thing"
    assert state["tasks"]["agent"]["route"]["executor"] == "agent-cli"


def test_v01_project_without_models_is_upgraded_lazily(tmp_path: Path) -> None:
    target = autodev_dir(tmp_path)
    target.mkdir(parents=True)
    (target / "plan.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "project": "demo",
                "tasks": [
                    {
                        "id": "old",
                        "title": "Old",
                        "model": "NONE",
                        "command": [sys.executable, "-c", "pass"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    catalog = load_models(tmp_path)
    assert (target / "models.yaml").exists()
    assert catalog.profiles[ModelLevel.NONE].executor == "command"
