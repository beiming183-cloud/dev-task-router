from __future__ import annotations

from dev_task_router.config import (
    load_rolling_context,
    save_rolling_context,
    write_default_files,
)
from dev_task_router.handoff import HandoffWriter
from dev_task_router.models import Plan, TaskStatus
from dev_task_router.repo_context import RepositoryContext
from dev_task_router.rolling_context import (
    ContextBudget,
    ContextPackBuilder,
    RollingProjectContext,
)
from dev_task_router.state import StateStore


def _plan() -> Plan:
    return Plan.from_dict(
        {
            "version": 3,
            "project": "demo",
            "stages": [
                {
                    "id": "stage2",
                    "title": "Stage 2",
                    "steps": [
                        {
                            "id": "cursor",
                            "title": "Cursor",
                            "tasks": [
                                {
                                    "id": "semantic-cursor",
                                    "title": "Implement semantic cursor",
                                    "kind": "complex_code",
                                    "prompt": "Implement semantic cursor movement without changing history semantics.",
                                    "acceptance": [
                                        "cursor movement tests pass",
                                        "history behavior is unchanged",
                                        "copy/paste behavior is unchanged",
                                    ],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
    )


def _two_task_plan() -> Plan:
    return Plan.from_dict(
        {
            "version": 3,
            "project": "demo",
            "stages": [
                {
                    "id": "stage2",
                    "title": "Stage 2",
                    "steps": [
                        {
                            "id": "cursor",
                            "title": "Cursor",
                            "tasks": [
                                {
                                    "id": "done-task",
                                    "title": "Finished setup",
                                    "kind": "simple_edit",
                                    "prompt": "Finish setup",
                                },
                                {
                                    "id": "semantic-cursor",
                                    "title": "Implement semantic cursor",
                                    "kind": "complex_code",
                                    "prompt": "Implement semantic cursor movement.",
                                    "acceptance": ["cursor tests pass"],
                                },
                            ],
                        }
                    ],
                }
            ],
        }
    )


def test_rolling_context_deduplicates_and_detects_stale_commit() -> None:
    context = RollingProjectContext.from_dict(
        {
            "project": "demo",
            "goal": "  Keep one canonical conversation   for the project. ",
            "decisions": ["SelectionState is the source of truth", "selectionstate is the source of truth"],
            "constraints": ["Do not break history", "Do not break history"],
            "stage_notes": {"stage2": ["Preserve semantic DEL"]},
            "task_notes": {"semantic-cursor": ["Drag should feel continuous"]},
            "last_commit": "abc123",
        }
    )
    repo = RepositoryContext(repository="owner/repo", commit="def456")

    assert context.goal == "Keep one canonical conversation for the project."
    assert context.decisions == ("SelectionState is the source of truth",)
    assert context.constraints == ("Do not break history",)
    assert context.item_count == 4
    assert context.is_stale_against(repo) is True


def test_context_pack_keeps_task_specific_context_under_budget(tmp_path) -> None:
    plan = _plan()
    state = StateStore(tmp_path).create(plan)
    state["tasks"]["semantic-cursor"]["failures"] = [
        {"type": "CHECK", "message": "old failure"},
        {"type": "REVIEW", "message": "latest failure"},
    ]
    StateStore(tmp_path).save(state)

    rolling = RollingProjectContext.from_dict(
        {
            "project": "demo",
            "goal": "Improve cursor interaction without losing existing behavior.",
            "decisions": ["d1", "d2", "d3"],
            "constraints": ["c1", "c2", "c3"],
            "stage_notes": {"stage2": ["s1", "s2", "s3"]},
            "task_notes": {"semantic-cursor": ["t1", "t2", "t3"]},
            "last_commit": "abc123",
        }
    )
    repo = RepositoryContext.from_dict(
        {
            "repository": "owner/repo",
            "branch": "feature/cursor",
            "commit": "abc123",
            "relevant_files": ["src/Cursor.kt", "src/Selection.kt", "src/History.kt"],
            "test_files": ["tests/CursorTest.kt"],
            "ci_status": "success",
            "facts": ["SelectionState owns the selection", "History tests currently pass"],
        }
    )
    budget = ContextBudget(
        max_decisions=2,
        max_constraints=2,
        max_stage_notes=2,
        max_task_notes=2,
        max_repo_files=2,
        max_repo_facts=1,
        max_failures=1,
        max_acceptance=2,
    )
    pack = ContextPackBuilder(budget).build(
        plan,
        state,
        plan.tasks[0],
        rolling,
        repository=repo,
        requested_route={"level": "HIGH", "model": "high", "executor": "command"},
    )

    assert pack.decisions == ("d2", "d3")
    assert pack.constraints == ("c2", "c3")
    assert pack.stage_notes == ("s2", "s3")
    assert pack.task_notes == ("t2", "t3")
    assert pack.acceptance == (
        "history behavior is unchanged",
        "copy/paste behavior is unchanged",
    )
    assert pack.failures == ("REVIEW: latest failure",)
    assert pack.repository is not None
    assert pack.repository["files"] == ["src/Cursor.kt", "src/Selection.kt"]
    assert pack.repository["facts"] == ["SelectionState owns the selection"]
    assert pack.stale_context is False
    assert pack.omitted["decisions"] == 1
    assert "Task Context Pack" in pack.to_markdown()
    assert "Exact next action" in pack.to_markdown()


def test_context_pack_marks_commit_sensitive_context_stale(tmp_path) -> None:
    plan = _plan()
    state = StateStore(tmp_path).create(plan)
    rolling = RollingProjectContext.from_dict(
        {"project": "demo", "last_commit": "old-sha", "constraints": ["keep AC behavior"]}
    )
    repo = RepositoryContext(repository="owner/repo", commit="new-sha")

    pack = ContextPackBuilder().build(plan, state, plan.tasks[0], rolling, repository=repo)

    assert pack.stale_context is True
    assert "older commit" in pack.to_markdown()


def test_default_project_persists_empty_rolling_context(tmp_path) -> None:
    paths = write_default_files(tmp_path, "demo")
    context = load_rolling_context(tmp_path, project="demo")

    assert any(path.name == "context.yaml" for path in paths)
    assert context.project == "demo"
    assert context.item_count == 0

    updated = RollingProjectContext.from_dict(
        {
            "project": "demo",
            "goal": "Keep the same conversation while switching reasoning effort.",
            "decisions": ["Task decomposition is not conversation decomposition"],
        }
    )
    save_rolling_context(tmp_path, updated)
    loaded = load_rolling_context(tmp_path, project="demo")
    assert loaded.goal.startswith("Keep the same conversation")
    assert loaded.decisions == ("Task decomposition is not conversation decomposition",)


def test_handoff_prioritizes_next_task_pack_and_omits_passed_task_rows(tmp_path) -> None:
    plan = _two_task_plan()
    write_default_files(tmp_path, "demo")
    state = StateStore(tmp_path).create(plan)
    state["tasks"]["done-task"]["status"] = TaskStatus.PASSED.value
    StateStore(tmp_path).save(state)
    save_rolling_context(
        tmp_path,
        RollingProjectContext.from_dict(
            {
                "project": "demo",
                "goal": "Keep one conversation and preserve interaction semantics.",
                "constraints": ["Do not break history"],
            }
        ),
    )

    path = HandoffWriter(tmp_path).write(plan, StateStore(tmp_path).load())
    text = path.read_text(encoding="utf-8")

    assert "## Next Task Context Pack" in text
    assert "Implement semantic cursor" in text
    assert "Do not break history" in text
    assert "same canonical project conversation" in text
    assert "| stage2 | cursor | EXECUTOR | done-task |" not in text
    assert "| stage2 | cursor | EXECUTOR | semantic-cursor |" in text
