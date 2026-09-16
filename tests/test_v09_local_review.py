from __future__ import annotations

import json
import sys

import yaml

from dev_task_router.config import autodev_dir, load_models, write_default_files
from dev_task_router.execution_evidence import ExecutionEvidenceLedger
from dev_task_router.local_review import IndependentLocalReviewer, LocalReviewerConfig
from dev_task_router.local_session import LocalSessionStore
from dev_task_router.models import Plan
from dev_task_router.router import RuleRouter
from dev_task_router.state import StateStore


def _plan(*, max_attempts: int = 2) -> Plan:
    return Plan.from_dict(
        {
            "version": 3,
            "project": "demo",
            "tasks": [
                {
                    "id": "task",
                    "title": "Implement reviewed feature",
                    "kind": "normal_code",
                    "prompt": "Implement reviewed feature.",
                    "acceptance": ["reviewer approves"],
                    "review": True,
                    "review_level": "HIGH",
                    "max_attempts": max_attempts,
                    "escalate_after": 1,
                }
            ],
        }
    )


def _configure_reviewer(tmp_path, verdict: str) -> None:
    path = autodev_dir(tmp_path) / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["profiles"]["HIGH"] = {
        "provider": "fake-independent-reviewer",
        "model": "review-model",
        "executor": "agent-cli",
        "command": [sys.executable, "-c", f"print({verdict!r})"],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _ready(tmp_path, verdict: str = "PASS approved", *, max_attempts: int = 2):
    plan = _plan(max_attempts=max_attempts)
    write_default_files(tmp_path, plan.project)
    _configure_reviewer(tmp_path, verdict)
    store = StateStore(tmp_path)
    store.create(plan)
    state = store.load()
    item = state["tasks"]["task"]
    item["status"] = "RUNNING"
    item["attempts"] = 1
    item["local_dispatch_id"] = "d1"
    item["route"] = {
        "level": "MEDIUM",
        "provider": "local",
        "model": "medium",
        "executor": "command",
        "reason": "test",
        "confidence": "medium",
        "traits": [],
    }
    state["status"] = "RUNNING"
    state["current_task"] = "task"
    store.save(state)
    sessions = {
        "version": 1,
        "sessions": {
            "d1": {
                "task_id": "task",
                "status": "REVIEW_REQUIRED",
                "response_digest": "response-digest",
                "check": {
                    "ok": True,
                    "message": "checks passed",
                    "failure_type": None,
                    "returncode": 0,
                },
            }
        },
    }
    (autodev_dir(tmp_path) / "local-sessions.json").write_text(
        json.dumps(sessions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    router = RuleRouter(load_models(tmp_path))
    evidence = ExecutionEvidenceLedger(tmp_path)
    return plan, store, router, LocalSessionStore(tmp_path), evidence


def _enabled_config() -> LocalReviewerConfig:
    return LocalReviewerConfig(
        enabled=True,
        allowed_executors=("agent-cli",),
        allowed_providers=("fake-independent-reviewer",),
    )


def test_independent_reviewer_passes_without_incrementing_implementation_attempt(tmp_path) -> None:
    plan, store, router, sessions, evidence = _ready(tmp_path, "PASS reviewer approved")
    runner = IndependentLocalReviewer(
        tmp_path,
        plan,
        store,
        router,
        sessions,
        config=_enabled_config(),
        evidence=evidence,
    )

    result = runner.run("task", "d1")
    state = store.load()

    assert result.status == "PASSED"
    assert state["tasks"]["task"]["status"] == "PASSED"
    assert state["tasks"]["task"]["attempts"] == 1
    assert state["tasks"]["task"]["review"]["ok"] is True
    assert sessions.get("d1")["status"] == "PASSED"
    assert [event.kind for event in evidence.events_for_dispatch("d1")] == [
        "REVIEW_STARTED",
        "REVIEWED",
        "STATE_RECORDED",
    ]


def test_explicit_review_fail_reuses_current_attempt_and_allows_new_implementation_attempt(tmp_path) -> None:
    plan, store, router, sessions, evidence = _ready(tmp_path, "FAIL acceptance missing")
    runner = IndependentLocalReviewer(
        tmp_path,
        plan,
        store,
        router,
        sessions,
        config=_enabled_config(),
        evidence=evidence,
    )

    result = runner.run("task", "d1")
    state = store.load()

    assert result.status == "REVIEW_FAILED"
    assert state["tasks"]["task"]["status"] == "FAILED"
    assert state["tasks"]["task"]["attempts"] == 1
    assert state["tasks"]["task"]["last_failure_type"] == "REVIEW"
    assert len(state["tasks"]["task"]["failures"]) == 1
    assert state["status"] == "READY"
    assert state["current_task"] is None
    assert sessions.get("d1")["status"] == "REVIEW_FAILED"


def test_review_protocol_failure_is_infrastructure_and_keeps_review_required(tmp_path) -> None:
    plan, store, router, sessions, evidence = _ready(tmp_path, "MAYBE looks fine")
    runner = IndependentLocalReviewer(
        tmp_path,
        plan,
        store,
        router,
        sessions,
        config=_enabled_config(),
        evidence=evidence,
    )

    result = runner.run("task", "d1")
    state = store.load()

    assert result.status == "REVIEW_INFRASTRUCTURE"
    assert result.infrastructure_failure is True
    assert state["tasks"]["task"]["status"] == "RUNNING"
    assert state["tasks"]["task"]["attempts"] == 1
    assert state["tasks"]["task"]["last_failure_type"] is None
    assert sessions.get("d1")["status"] == "REVIEW_REQUIRED"
    assert evidence.latest_for_dispatch("d1").data["verdict"] == "ERROR"


def test_disabled_independent_reviewer_does_not_fake_same_conversation_review(tmp_path) -> None:
    plan, store, router, sessions, evidence = _ready(tmp_path, "PASS reviewer approved")
    runner = IndependentLocalReviewer(
        tmp_path,
        plan,
        store,
        router,
        sessions,
        config=LocalReviewerConfig(enabled=False),
        evidence=evidence,
    )

    result = runner.run("task", "d1")

    assert result.status == "REVIEW_REQUIRED"
    assert result.infrastructure_failure is True
    assert "disabled" in result.message
    assert store.load()["tasks"]["task"]["attempts"] == 1
    assert sessions.get("d1")["status"] == "REVIEW_REQUIRED"
    assert evidence.events_for_dispatch("d1") == ()


def test_reviewer_exhaustion_blocks_without_double_counting_attempt(tmp_path) -> None:
    plan, store, router, sessions, evidence = _ready(
        tmp_path,
        "FAIL final review failed",
        max_attempts=1,
    )
    runner = IndependentLocalReviewer(
        tmp_path,
        plan,
        store,
        router,
        sessions,
        config=_enabled_config(),
        evidence=evidence,
    )

    result = runner.run("task", "d1")
    state = store.load()

    assert result.status == "FAILED"
    assert state["status"] == "FAILED"
    assert state["tasks"]["task"]["attempts"] == 1
