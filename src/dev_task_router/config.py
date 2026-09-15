from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import Plan


AUTODEV_DIR = ".autodev"
PLAN_FILE = "plan.yaml"
PROJECT_FILE = "project.yaml"
STATE_FILE = "state.json"


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


def write_default_files(root: Path, project_name: str) -> list[Path]:
    target = autodev_dir(root)
    target.mkdir(parents=True, exist_ok=True)

    project_path = target / PROJECT_FILE
    plan_path = target / PLAN_FILE

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

    if not plan_path.exists():
        plan_path.write_text(
            yaml.safe_dump(
                {
                    "version": 1,
                    "project": project_name,
                    "tasks": [
                        {
                            "id": "hello",
                            "title": "V0.1 smoke task",
                            "model": "NONE",
                            "command": ["python", "-c", "print('Dev Task Router V0.1 is running')"],
                            "checks": [],
                        }
                    ],
                },
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    return [project_path, plan_path]
