from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from dev_task_router.cli import main
from dev_task_router.config import autodev_dir, load_plan, write_default_files
from dev_task_router.state import StateStore
from dev_task_router.workflow import WorkflowEngine


def write_plan(root: Path, task: dict) -> None:
    (autodev_dir(root) / "plan.yaml").write_text(
        yaml.safe_dump(
            {"version": 3, "project": "demo", "tasks": [task]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def test_retry_succeeds_on_second_attempt(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    code = (
        "from pathlib import Path; "
        "p=Path('count.txt'); n=int(p.read_text() if p.exists() else '0')+1; "
        "p.write_text(str(n)); raise SystemExit(0 if n>=2 else 7)"
    )
    write_plan(
        tmp_path,
        {
            "id": "retry",
            "title": "retry once",
            "kind": "normal_code",
            "max_attempts": 2,
            "command": [sys.executable, "-c", code],
        },
    )
    plan = load_plan(tmp_path)
    state = WorkflowEngine(tmp_path, plan, StateStore(tmp_path)).run()
    assert state["status"] == "PASSED"
    assert state["tasks"]["retry"]["attempts"] == 2
    assert [item["level"] for item in state["tasks"]["retry"]["route_history"]] == [
        "MEDIUM",
        "MEDIUM",
    ]


def test_third_attempt_escalates_medium_to_high(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    code = (
        "from pathlib import Path; "
        "p=Path('count.txt'); n=int(p.read_text() if p.exists() else '0')+1; "
        "p.write_text(str(n)); raise SystemExit(0 if n>=3 else 9)"
    )
    write_plan(
        tmp_path,
        {
            "id": "escalate",
            "title": "escalate",
            "kind": "normal_code",
            "max_attempts": 3,
            "escalate_after": 2,
            "command": [sys.executable, "-c", code],
        },
    )
    state = WorkflowEngine(tmp_path, load_plan(tmp_path), StateStore(tmp_path)).run()
    history = state["tasks"]["escalate"]["route_history"]
    assert [item["level"] for item in history] == ["MEDIUM", "MEDIUM", "HIGH"]
    assert state["status"] == "PASSED"


def test_exhausted_retry_budget_becomes_blocked(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    write_plan(
        tmp_path,
        {
            "id": "broken",
            "title": "broken",
            "kind": "normal_code",
            "max_attempts": 2,
            "command": [sys.executable, "-c", "raise SystemExit(4)"],
        },
    )
    state = WorkflowEngine(tmp_path, load_plan(tmp_path), StateStore(tmp_path)).run()
    assert state["status"] == "BLOCKED"
    assert state["tasks"]["broken"]["status"] == "BLOCKED"
    assert state["tasks"]["broken"]["attempts"] == 2
    assert len(state["tasks"]["broken"]["failures"]) == 2
    assert state["tasks"]["broken"]["last_failure_type"] == "EXECUTOR"


def test_require_diff_rejects_no_change(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    write_default_files(tmp_path, "demo")
    # Ignore AutoDev's own runtime files so they do not count as task output.
    (tmp_path / ".gitignore").write_text(".autodev/\n", encoding="utf-8")
    subprocess.run(["git", "add", ".gitignore"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=test", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    write_plan(
        tmp_path,
        {
            "id": "no-diff",
            "title": "no diff",
            "kind": "normal_code",
            "require_diff": True,
            "command": [sys.executable, "-c", "pass"],
        },
    )
    state = WorkflowEngine(tmp_path, load_plan(tmp_path), StateStore(tmp_path)).run()
    assert state["status"] == "FAILED"
    assert state["tasks"]["no-diff"]["last_failure_type"] == "DIFF"


def configure_high_reviewer(root: Path, verdict: str) -> None:
    path = autodev_dir(root) / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["profiles"]["HIGH"] = {
        "provider": "fake-reviewer",
        "model": "review-model",
        "executor": "agent-cli",
        "command": [sys.executable, "-c", f"print({verdict!r})"],
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_independent_reviewer_can_pass_task(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    configure_high_reviewer(tmp_path, "PASS reviewer approved")
    write_plan(
        tmp_path,
        {
            "id": "reviewed",
            "title": "reviewed task",
            "kind": "normal_code",
            "review": True,
            "acceptance": ["command completes", "reviewer approves"],
            "command": [sys.executable, "-c", "print('work done')"],
        },
    )
    state = WorkflowEngine(tmp_path, load_plan(tmp_path), StateStore(tmp_path)).run()
    assert state["status"] == "PASSED"
    assert state["tasks"]["reviewed"]["review"]["ok"] is True
    assert state["tasks"]["reviewed"]["review"]["level"] == "HIGH"


def test_reviewer_failure_retries_then_blocks(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    configure_high_reviewer(tmp_path, "FAIL missing acceptance")
    write_plan(
        tmp_path,
        {
            "id": "review-fail",
            "title": "review fail",
            "kind": "normal_code",
            "review": True,
            "max_attempts": 2,
            "command": [sys.executable, "-c", "pass"],
        },
    )
    state = WorkflowEngine(tmp_path, load_plan(tmp_path), StateStore(tmp_path)).run()
    assert state["status"] == "BLOCKED"
    assert state["tasks"]["review-fail"]["last_failure_type"] == "REVIEW"
    assert state["tasks"]["review-fail"]["attempts"] == 2


def test_manual_retry_resets_budget_but_preserves_history(tmp_path: Path) -> None:
    write_default_files(tmp_path, "demo")
    write_plan(
        tmp_path,
        {
            "id": "manual",
            "title": "manual",
            "max_attempts": 2,
            "command": [sys.executable, "-c", "raise SystemExit(1)"],
        },
    )
    plan = load_plan(tmp_path)
    store = StateStore(tmp_path)
    state = WorkflowEngine(tmp_path, plan, store).run()
    assert state["status"] == "BLOCKED"
    assert main(["--root", str(tmp_path), "retry", "manual"]) == 0
    state = store.load()
    assert state["status"] == "READY"
    assert state["tasks"]["manual"]["status"] == "PENDING"
    assert state["tasks"]["manual"]["attempts"] == 0
    assert state["tasks"]["manual"]["retry_cycles"] == 1
    assert len(state["tasks"]["manual"]["failures"]) == 2
