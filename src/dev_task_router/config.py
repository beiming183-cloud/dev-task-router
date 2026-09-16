from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .mode_switch import LocalSwitchConfig
from .models import Plan
from .repo_context import RepositoryContext
from .rolling_context import RollingProjectContext
from .router import ModelCatalog
from .surface import SurfaceCatalog


AUTODEV_DIR = ".autodev"
PLAN_FILE = "plan.yaml"
PROJECT_FILE = "project.yaml"
MODELS_FILE = "models.yaml"
SURFACES_FILE = "surfaces.yaml"
REPO_CONTEXT_FILE = "repo-context.yaml"
ROLLING_CONTEXT_FILE = "context.yaml"
LOCAL_SWITCH_FILE = "local-switch.yaml"
LOCAL_CONVERSATION_FILE = "local-conversation.yaml"
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


def load_surfaces(root: Path) -> SurfaceCatalog:
    path = autodev_dir(root) / SURFACES_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(default_surfaces(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return SurfaceCatalog.from_dict(load_yaml(path))


def load_repository_context(root: Path) -> RepositoryContext | None:
    path = autodev_dir(root) / REPO_CONTEXT_FILE
    if not path.exists():
        return None
    return RepositoryContext.from_dict(load_yaml(path))


def save_repository_context(root: Path, context: RepositoryContext) -> Path:
    path = autodev_dir(root) / REPO_CONTEXT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(context.to_dict(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def load_rolling_context(root: Path, *, project: str | None = None) -> RollingProjectContext:
    path = autodev_dir(root) / ROLLING_CONTEXT_FILE
    if not path.exists():
        if project is None:
            project = load_plan(root).project
        context = RollingProjectContext.empty(project)
        save_rolling_context(root, context)
        return context
    context = RollingProjectContext.from_dict(load_yaml(path))
    if project is not None and context.project != project:
        raise ValueError("rolling context project does not match plan project")
    return context


def save_rolling_context(root: Path, context: RollingProjectContext) -> Path:
    path = autodev_dir(root) / ROLLING_CONTEXT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(context.to_dict(), allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return path


def load_local_switch(root: Path) -> LocalSwitchConfig:
    path = autodev_dir(root) / LOCAL_SWITCH_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(default_local_switch(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return LocalSwitchConfig.from_dict(load_yaml(path))


def load_local_conversation_dict(root: Path) -> dict[str, Any]:
    path = autodev_dir(root) / LOCAL_CONVERSATION_FILE
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(default_local_conversation(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    return load_yaml(path)


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


def default_surfaces() -> dict[str, Any]:
    return {
        "version": 1,
        "default_surface": "chat",
        "surfaces": {
            "chat": {
                "strategy": "fixed",
                "routes": {
                    "LOW": {"family": "sol", "effort": "low", "label": "5.6 Sol Low"},
                    "MEDIUM": {
                        "family": "sol",
                        "effort": "medium",
                        "label": "5.6 Sol Medium",
                    },
                    "HIGH": {"family": "sol", "effort": "high", "label": "5.6 Sol High"},
                },
            },
            "codex": {
                "strategy": "pool",
                "families": ["lunar", "terra", "sol", "astra"],
                "efforts": ["low", "medium", "high"],
                "routes": {},
            },
            "work": {
                "strategy": "pool",
                "families": ["lunar", "terra", "sol", "astra"],
                "efforts": ["low", "medium", "high"],
                "routes": {},
            },
        },
    }


def default_local_switch() -> dict[str, Any]:
    return {
        "version": 1,
        "enabled": False,
        "backend": "windows-uia",
        "window": {"title_regex": ".*ChatGPT.*"},
        "selector": {"open_labels": []},
        "family_labels": {"sol": []},
        "effort_labels": {"low": [], "medium": [], "high": []},
        "verify_labels": {"low": [], "medium": [], "high": []},
    }


def default_local_conversation() -> dict[str, Any]:
    """Safe-by-default current-conversation UIA configuration.

    It is intentionally disabled and uncalibrated. No Task can be submitted until
    the user's current ChatGPT build exposes and verifies the composer/send controls.
    """
    return {
        "version": 1,
        "enabled": False,
        "backend": "windows-uia",
        "window": {"title_regex": ".*ChatGPT.*"},
        "composer": {
            "labels": [],
            "control_types": ["Edit", "Document"],
        },
        "send": {
            "labels": [],
            "control_types": ["Button"],
        },
        "limits": {
            "max_prompt_chars": 60000,
        },
    }


def write_default_files(root: Path, project_name: str) -> list[Path]:
    target = autodev_dir(root)
    target.mkdir(parents=True, exist_ok=True)

    project_path = target / PROJECT_FILE
    plan_path = target / PLAN_FILE
    models_path = target / MODELS_FILE
    surfaces_path = target / SURFACES_FILE
    context_path = target / ROLLING_CONTEXT_FILE
    local_switch_path = target / LOCAL_SWITCH_FILE
    local_conversation_path = target / LOCAL_CONVERSATION_FILE

    if not project_path.exists():
        project_path.write_text(
            yaml.safe_dump(
                {"version": 1, "name": project_name, "commands": {"test": [], "build": []}},
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

    if not surfaces_path.exists():
        surfaces_path.write_text(
            yaml.safe_dump(default_surfaces(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    if not context_path.exists():
        context_path.write_text(
            yaml.safe_dump(
                RollingProjectContext.empty(project_name).to_dict(),
                allow_unicode=True,
                sort_keys=False,
            ),
            encoding="utf-8",
        )

    if not local_switch_path.exists():
        local_switch_path.write_text(
            yaml.safe_dump(default_local_switch(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    if not local_conversation_path.exists():
        local_conversation_path.write_text(
            yaml.safe_dump(default_local_conversation(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    if not plan_path.exists():
        plan_path.write_text(
            yaml.safe_dump(
                {
                    "version": 3,
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
                                            "title": "V0.8 smoke task",
                                            "kind": "test",
                                            "role": "EXECUTOR",
                                            "max_attempts": 1,
                                            "command": [
                                                "python",
                                                "-c",
                                                "print('Dev Task Router V0.8 is running')",
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

    return [
        project_path,
        plan_path,
        models_path,
        surfaces_path,
        context_path,
        local_switch_path,
        local_conversation_path,
    ]
