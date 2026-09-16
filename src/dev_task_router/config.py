from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Plan
from .router import ModelCatalog


AUTODEV_DIR = ".autodev"
PLAN_FILE = "plan.yaml"
PROJECT_FILE = "project.yaml"
MODELS_FILE = "models.yaml"
STATE_FILE = "state.json"
HANDOFF_FILE = "handoff.md"
USAGE_FILE = "usage.jsonl"


def autodev_dir(root: Path) -> Path:
    return root / AUTODEV_DIR


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping")
    return data


def load_plan(root: Path) -> Plan:
    return Plan.from_dict(load_yaml(autodev_dir(root) / PLAN_FILE))


def load_models(root: Path) -> ModelCatalog:
    path = autodev_dir(root) / MODELS_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(default_models(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return ModelCatalog.from_dict(load_yaml(path))


def default_models() -> dict[str, Any]:
    return {
        "version": 1,
        "profiles": {
            "NONE": {"provider": "local", "model": "none", "executor": "command"},
            "LOW": {"provider": "local", "model": "low", "executor": "command"},
            "MEDIUM": {"provider": "local", "model": "medium", "executor": "command"},
            "HIGH": {"provider": "local", "model": "high", "executor": "command"},
        },
        "rules": {
            "repo_search": "LOW",
            "docs": "LOW",
            "handoff": "LOW",
            "simple_edit": "LOW",
            "normal_code": "MEDIUM",
            "normal_debug": "MEDIUM",
            "architecture": "HIGH",
            "planning": "HIGH",
            "complex_code": "HIGH",
            "hard_debug": "HIGH",
            "review": "HIGH",
            "test": "NONE",
            "build": "NONE",
        },
    }


def write_default_files(root: Path, project_name: str) -> list[Path]:
    target = autodev_dir(root)
    target.mkdir(parents=True, exist_ok=True)

    project_path = target / PROJECT_FILE
    plan_path = target / PLAN_FILE
    models_path = target / MODELS_FILE

    if not project_path.exists():
        project_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "name": project_name,
                    "commands": {"test": [], "build": []},
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    if not models_path.exists():
        models_path.write_text(
            yaml.safe_dump(default_models(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    if not plan_path.exists():
        plan_path.write_text(
            yaml.safe_dump(
                {
                    "version": 2,
                    "project": project_name,
                    "stages": [
                        {
                            "id": "bootstrap",
                            "title": "Bootstrap",
                            "steps": [
                                {
                                    "id": "smoke",
                                    "title": "Smoke test",
                                    "tasks": [
                                        {
                                            "id": "hello",
                                            "title": "V0.2 smoke task",
                                            "kind": "test",
                                            "role": "EXECUTOR",
                                            "command": [
                                                "python",
                                                "-c",
                                                "print('Dev Task Router V0.2 is running')",
                                            ],
                                            "checks": [],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    return [project_path, plan_path, models_path]
