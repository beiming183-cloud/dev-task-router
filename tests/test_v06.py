from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

from dev_task_router.classifier import DifficultyClassifier
from dev_task_router.cli import main
from dev_task_router.config import (
    autodev_dir,
    load_plan,
    load_repository_context,
    save_repository_context,
    write_default_files,
)
from dev_task_router.handoff import HandoffWriter
from dev_task_router.models import ModelLevel, TaskSpec
from dev_task_router.repo_context import RepositoryContext
from dev_task_router.state import StateStore
from dev_task_router.workflow import WorkflowEngine


def test_repository_context_parses_deduplicates_and_compacts() -> None:
    context = RepositoryContext.from_dict(
        {
            "repository": "owner/repo",
            "branch": "feature/x",
            "commit": "abc123",
            "pr_number": 7,
            "relevant_files": ["src/a.py", "src/a.py", "src/b.py"],
            "changed_files": ["src/a.py"],
            "test_files": ["tests/test_a.py"],
            "ci_status": "success",
            "ci_checks": ["pytest", "build"],
            "evidence_tags": ["Public-API"],
            "facts": ["A calls B"],
        }
    )
    assert context.relevant_files == ("src/a.py", "src/b.py")
    assert context.evidence_tags == ("public-api",)
    assert context.all_files == ("src/a.py", "src/b.py", "tests/test_a.py")
    compact = context.compact(max_files=2)
    assert compact["commit"] == "abc123"
    assert compact["files"] == ["src/a.py", "src/b.py"]
    assert compact["file_count_total"] == 3


def test_repository_context_rejects_unsafe_paths() -> None:
    with pytest.raises(ValueError, match="unsafe path"):
        RepositoryContext.from_dict(
            {"repository": "owner/repo", "relevant_files": ["../secret.txt"]}
        )


def test_broad_repo_scope_can_raise_medium_task_to_high() -> None:
    task = TaskSpec(
        id="feature",
        title="Implement feature",
        prompt="implement a normal feature using established interfaces",
        kind="normal_code",
    )
    base = DifficultyClassifier().classify(task)
    assert base.level == ModelLevel.MEDIUM

    context = RepositoryContext.from_dict(
        {
            "repository": "owner/repo",
            "commit": "deadbeef",
            "relevant_files": [
                "packages/ui/a.py",
                "packages/ui/b.py",
                "packages/core/c.py",
                "packages/core/d.py",
                "modules/history/e.py",
                "modules/history/f.py",
                "app/input/g.py",
                "tests/test_input.py",
            ],
        }
    )
    assessed = DifficultyClassifier().classify(task, context)
    assert assessed.level == ModelLevel.HIGH
    assert "cross-module" in assessed.traits
    assert "commit-anchored" in assessed.traits
    assert any("repo evidence" in item for item in assessed.factors)


def test_localized_repo_evidence_does_not_inflate_simple_edit() -> None:
    task = TaskSpec(
        id="label",
        title="Rename label",
        prompt="rename one UI label",
        kind="simple_edit",
    )
    context = RepositoryContext.from_dict(
        {
            "repository": "owner/repo",
            "commit": "abc",
            "relevant_files": ["src/ui/labels.py"],
            "ci_status": "success",
        }
    )
    assessed = DifficultyClassifier().classify(task, context)
    assert assessed.level == ModelLevel.LOW
    assert "localized" in assessed.traits


def test_verified_high_risk_repo_tag_catches_pseudo_simple_change() -> None:
    task = TaskSpec(
        id="config",
        title="Adjust config default",
        prompt="change the default value in one configuration entry",
        kind="simple_edit",
    )
    context = RepositoryContext.from_dict(
        {
            "repository": "owner/repo",
            "commit": "abc",
            "relevant_files": ["src/config.py"],
            "evidence_tags": ["auth"],
        }
    )
    assessed = DifficultyClassifier().classify(task, context)
    assert assessed.level == ModelLevel.HIGH
    assert "high-risk" in assessed.traits


def test_repo_context_roundtrip_cli_and_workflow_route(tmp_path: Path, capsys) -> None:
    write_default_files(tmp_path, "demo")
    input_path = tmp_path / "repo.json"
    input_path.write_text(
        json.dumps(
            {
                "repository": "owner/demo",
                "branch": "main",
                "commit": "1234567",
                "relevant_files": ["src/demo.py"],
                "test_files": ["tests/test_demo.py"],
                "ci_status": "success",
                "ci_checks": ["pytest"],
            }
        ),
        encoding="utf-8",
    )
    assert main(["--root", str(tmp_path), "repo-context", "--import", str(input_path)]) == 0
    loaded = load_repository_context(tmp_path)
    assert loaded is not None and loaded.commit == "1234567"

    plan_path = autodev_dir(tmp_path) / "plan.yaml"
    plan_path.write_text(
        yaml.safe_dump(
            {
                "version": 3,
                "project": "demo",
                "tasks": [
                    {
                        "id": "work",
                        "title": "Implement normal feature",
                        "kind": "normal_code",
                        "command": [sys.executable, "-c", "print('ok')"],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    plan = load_plan(tmp_path)
    state = WorkflowEngine(tmp_path, plan, StateStore(tmp_path)).run()
    route = state["tasks"]["work"]["route"]
    assert "commit-anchored" in route["traits"]
    assert route["confidence"] in {"medium", "high"}

    assert main(["--root", str(tmp_path), "repo-context", "--json"]) == 0
    out = capsys.readouterr().out
    assert "owner/demo" in out and "1234567" in out


def test_handoff_includes_repository_anchor_and_verified_files(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    context = RepositoryContext.from_dict(
        {
            "repository": "owner/demo",
            "branch": "feature/x",
            "commit": "cafebabe",
            "pr_number": 12,
            "relevant_files": ["src/core.py"],
            "test_files": ["tests/test_core.py"],
            "ci_status": "failure",
            "ci_checks": ["pytest"],
            "facts": ["core.py owns the state transition"],
        }
    )
    save_repository_context(tmp_path, context)
    plan = load_plan(tmp_path)
    store = StateStore(tmp_path)
    state = store.ensure_for_plan(plan)
    path = HandoffWriter(tmp_path).write(plan, state)
    text = path.read_text(encoding="utf-8")
    assert "## Repository evidence" in text
    assert "owner/demo" in text
    assert "cafebabe" in text
    assert "src/core.py" in text
    assert "core.py owns the state transition" in text
