from __future__ import annotations

import sys
from pathlib import Path

import yaml

from dev_task_router.classifier import DifficultyClassifier
from dev_task_router.config import autodev_dir, load_models, load_plan, load_surfaces, write_default_files
from dev_task_router.models import ModelLevel, TaskSpec
from dev_task_router.router import RuleRouter
from dev_task_router.state import StateStore
from dev_task_router.workflow import WorkflowEngine


def task(title: str, *, kind: str = "normal_code", prompt: str | None = None, **extra) -> TaskSpec:
    data = {
        "id": "t",
        "title": title,
        "kind": kind,
        "prompt": prompt or title,
        **extra,
    }
    return TaskSpec.from_dict(data)


def test_content_classifier_handles_low_medium_high_and_none() -> None:
    classifier = DifficultyClassifier()

    none_task = TaskSpec.from_dict(
        {
            "id": "test",
            "title": "run tests",
            "kind": "test",
            "command": [sys.executable, "-c", "pass"],
        }
    )
    assert classifier.classify(none_task).level == ModelLevel.NONE

    low = task("Rename one UI label", kind="simple_edit")
    assert classifier.classify(low).level == ModelLevel.LOW

    medium = task("Implement a normal feature in the existing module", kind="normal_code")
    assert classifier.classify(medium).level == ModelLevel.MEDIUM

    high = task(
        "Change authentication state across modules while preserving backward compatibility",
        kind="simple_edit",
    )
    assessment = classifier.classify(high)
    assert assessment.level == ModelLevel.HIGH
    assert "high-risk" in assessment.traits
    assert "cross-module" in assessment.traits


def test_chinese_core_semantics_are_high_even_when_kind_is_generic() -> None:
    assessment = DifficultyClassifier().classify(
        task("修改核心状态机和语义选区，保持历史状态与向后兼容", kind="normal_code")
    )
    assert assessment.level == ModelLevel.HIGH
    assert assessment.confidence in {"medium", "high"}


def test_rule_router_uses_content_classifier_but_explicit_level_still_wins(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    router = RuleRouter(load_models(tmp_path))

    risky = task("Security migration across modules", kind="simple_edit")
    decision = router.route(risky)
    assert decision.level == ModelLevel.HIGH
    assert decision.reason.startswith("classifier:")
    assert decision.confidence is not None

    explicit = TaskSpec.from_dict(
        {
            "id": "x",
            "title": "Security migration across modules",
            "kind": "simple_edit",
            "level": "LOW",
            "prompt": "Security migration across modules",
        }
    )
    explicit_decision = router.route(explicit)
    assert explicit_decision.level == ModelLevel.LOW
    assert explicit_decision.reason == "explicit task level"


def test_surface_catalog_separates_difficulty_from_runtime_model_pool(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    surfaces = load_surfaces(tmp_path)

    chat = surfaces.route(ModelLevel.HIGH, "chat")
    assert chat.resolved is True
    assert chat.model is not None
    assert chat.model.family == "sol"
    assert chat.model.effort == "high"

    codex = surfaces.route(ModelLevel.HIGH, "codex")
    assert codex.resolved is False
    assert codex.model is None
    assert codex.candidate_families == ("lunar", "terra", "sol", "astra")
    assert codex.candidate_efforts == ("low", "medium", "high")
    assert "do not invent" in codex.reason


def test_surface_pool_can_be_configured_without_changing_classifier(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    path = autodev_dir(tmp_path) / "surfaces.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["surfaces"]["codex"]["routes"] = {
        "HIGH": {"family": "astra", "effort": "high", "label": "configured high"}
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")

    route = load_surfaces(tmp_path).route(ModelLevel.HIGH, "codex")
    assert route.resolved is True
    assert route.model is not None
    assert route.model.family == "astra"


def test_failure_policy_promotes_on_next_attempt(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    plan_path = autodev_dir(tmp_path) / "plan.yaml"
    code = (
        "from pathlib import Path; "
        "p=Path('n.txt'); n=int(p.read_text() if p.exists() else '0')+1; "
        "p.write_text(str(n)); raise SystemExit(0 if n>=2 else 1)"
    )
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
                        "max_attempts": 2,
                        "escalate_after": 1,
                        "command": [sys.executable, "-c", code],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    state = WorkflowEngine(
        tmp_path,
        load_plan(tmp_path),
        StateStore(tmp_path),
    ).run()
    assert state["status"] == "PASSED"
    history = state["tasks"]["work"]["route_history"]
    assert [item["level"] for item in history] == ["MEDIUM", "HIGH"]
