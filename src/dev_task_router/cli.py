from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .config import (
    load_models,
    load_plan,
    load_repository_context,
    load_rolling_context,
    save_repository_context,
    save_rolling_context,
    write_default_files,
)
from .handoff import HandoffWriter
from .models import TaskStatus, WorkflowStatus
from .repo_context import RepositoryContext
from .rolling_context import ContextPackBuilder, RollingProjectContext
from .router import RuleRouter
from .state import StateStore
from .workflow import WorkflowEngine


def project_root(value: str | None) -> Path:
    return Path(value or ".").resolve()


def _read_mapping(path_text: str) -> dict:
    source = Path(path_text).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")
    if source.suffix.lower() == ".json":
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"{source} must contain a mapping")
    return data


def cmd_init(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    name = args.name or root.name or "project"
    paths = write_default_files(root, name)
    plan = load_plan(root)
    store = StateStore(root)
    if not store.exists():
        store.create(plan)
    HandoffWriter(root).write(plan, store.ensure_for_plan(plan))
    print("initialized:")
    for path in paths:
        print(f"  {path.relative_to(root)}")
    print("  .autodev/state.json")
    print("  .autodev/handoff.md")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    repository_context = load_repository_context(root)
    router = RuleRouter(load_models(root), repository_context=repository_context)
    print(f"project: {plan.project}")
    if repository_context is not None:
        anchor = repository_context.commit or repository_context.branch or "unanchored"
        print(f"repository: {repository_context.repository} @ {anchor}")
    for index, task in enumerate(plan.tasks, 1):
        route = router.route(task)
        extras: list[str] = []
        if task.max_attempts > 1:
            extras.append(f"retry={task.max_attempts}")
        if task.review:
            extras.append(f"review={task.review_level.value}")
        if task.require_diff:
            extras.append("require_diff")
        if route.confidence:
            extras.append(f"confidence={route.confidence}")
        suffix = f" [{' '.join(extras)}]" if extras else ""
        print(
            f"{index}. {task.stage_id}/{task.step_id} [{task.role.value}/{route.level.value}] "
            f"{task.id} - {task.title} -> {route.profile.provider}:{route.profile.model} "
            f"via {route.profile.executor} ({route.reason}){suffix}"
        )
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    catalog = load_models(project_root(args.root))
    for level, profile in catalog.profiles.items():
        print(f"{level.value}: {profile.provider}:{profile.model} via {profile.executor}")
    return 0


def cmd_repo_context(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    if args.import_file:
        context = RepositoryContext.from_dict(_read_mapping(args.import_file))
        path = save_repository_context(root, context)
        print(f"saved repository context: {path.relative_to(root)}")
        return 0

    context = load_repository_context(root)
    if context is None:
        print("repository context: none")
        return 0
    if args.json:
        print(json.dumps(context.to_dict(), ensure_ascii=False, indent=2))
        return 0
    print(f"repository: {context.repository}")
    print(f"branch: {context.branch or 'unknown'}")
    print(f"commit: {context.commit or 'unanchored'}")
    print(f"pr: {context.pr_number or 'none'}")
    print(f"ci: {context.ci_status}")
    print(f"relevant files: {len(context.all_files)}")
    if context.evidence_tags:
        print(f"tags: {', '.join(context.evidence_tags)}")
    return 0


def cmd_context(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    if args.import_file:
        context = RollingProjectContext.from_dict(_read_mapping(args.import_file))
        if context.project != plan.project:
            raise ValueError("rolling context project does not match plan project")
        path = save_rolling_context(root, context)
        print(f"saved rolling context: {path.relative_to(root)}")
        return 0

    context = load_rolling_context(root, project=plan.project)
    repo = load_repository_context(root)
    if args.json:
        data = context.to_dict()
        data["stale_against_repository"] = context.is_stale_against(repo)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    print(f"project: {context.project}")
    print(f"goal: {context.goal or 'unset'}")
    print(f"decisions: {len(context.decisions)}")
    print(f"constraints: {len(context.constraints)}")
    print(f"stage notes: {sum(len(v) for v in context.stage_notes.values())}")
    print(f"task notes: {sum(len(v) for v in context.task_notes.values())}")
    print(f"last commit: {context.last_commit or 'unanchored'}")
    print(f"stale: {'yes' if context.is_stale_against(repo) else 'no'}")
    return 0


def cmd_context_pack(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    by_id = {task.id: task for task in plan.tasks}
    if args.task not in by_id:
        raise ValueError(f"unknown task: {args.task}")
    task = by_id[args.task]
    store = StateStore(root)
    state = store.ensure_for_plan(plan)
    repo = load_repository_context(root)
    rolling = load_rolling_context(root, project=plan.project)
    route = RuleRouter(load_models(root), repository_context=repo).route(task)
    requested_route = {
        "level": route.level.value,
        "provider": route.profile.provider,
        "model": route.profile.model,
        "executor": route.profile.executor,
        "reason": route.reason,
        "confidence": route.confidence,
    }
    pack = ContextPackBuilder().build(
        plan,
        state,
        task,
        rolling,
        repository=repo,
        requested_route=requested_route,
    )
    if args.json:
        print(json.dumps(pack.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(pack.to_markdown(), end="")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    store = StateStore(root)
    state = store.ensure_for_plan(plan)

    if state["status"] == WorkflowStatus.PASSED.value:
        print("workflow already passed")
        return 0
    if state["status"] == WorkflowStatus.PAUSED.value:
        print("workflow is paused; use `autodev resume`")
        return 1
    if state["status"] in {WorkflowStatus.FAILED.value, WorkflowStatus.BLOCKED.value}:
        print("workflow failed/blocked; inspect it and use `autodev retry <task>`")
        return 1
    if state["status"] == WorkflowStatus.RUNNING.value:
        print("workflow is already marked RUNNING; pause it before resuming")
        return 1

    state = WorkflowEngine(root, plan, store).run()
    return 0 if state["status"] == WorkflowStatus.PASSED.value else 1


def cmd_pause(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    store = StateStore(root)
    state = store.load()

    if state["status"] == WorkflowStatus.PASSED.value:
        print("workflow already passed")
        return 0
    if state["status"] in {WorkflowStatus.FAILED.value, WorkflowStatus.BLOCKED.value}:
        print("workflow failed/blocked; it cannot be paused")
        return 1
    if state["status"] == WorkflowStatus.PAUSED.value:
        print("workflow already paused")
        return 0

    state["status"] = WorkflowStatus.PAUSED.value
    store.save(state)
    try:
        HandoffWriter(root).write(load_plan(root), state)
    except (FileNotFoundError, ValueError):
        pass
    print("workflow paused")
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    store = StateStore(root)
    state = store.ensure_for_plan(plan)

    if state["status"] == WorkflowStatus.PASSED.value:
        print("workflow already passed")
        return 0
    if state["status"] in {WorkflowStatus.FAILED.value, WorkflowStatus.BLOCKED.value}:
        print("workflow failed/blocked; use `autodev retry <task>` after inspection")
        return 1
    if state["status"] == WorkflowStatus.READY.value:
        print("workflow is ready; use `autodev start`")
        return 1
    if state["status"] == WorkflowStatus.RUNNING.value:
        print("workflow is already marked RUNNING; pause it before resuming")
        return 1

    state["status"] = WorkflowStatus.READY.value
    store.save(state)
    result = WorkflowEngine(root, plan, store).run()
    return 0 if result["status"] == WorkflowStatus.PASSED.value else 1


def cmd_retry(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    store = StateStore(root)
    state = store.ensure_for_plan(plan)
    if args.task not in state["tasks"]:
        raise ValueError(f"unknown task: {args.task}")
    current = state["tasks"][args.task]["status"]
    if current not in {TaskStatus.FAILED.value, TaskStatus.BLOCKED.value}:
        raise ValueError(f"task {args.task} is {current}; only FAILED/BLOCKED tasks can be retried")
    store.reset_task(plan, args.task)
    HandoffWriter(root).write(plan, store.load())
    print(f"task reset for retry: {args.task}")
    if args.run:
        result = WorkflowEngine(root, plan, store).run()
        return 0 if result["status"] == WorkflowStatus.PASSED.value else 1
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    store = StateStore(root)
    state = store.load()
    if args.json:
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    print(f"project: {state['project']}")
    print(f"status: {state['status']}")
    if state.get("current_task"):
        print(f"current: {state['current_task']}")

    for task_id, task_state in state["tasks"].items():
        marker = {
            TaskStatus.PASSED.value: "✓",
            TaskStatus.RUNNING.value: "▶",
            TaskStatus.FAILED.value: "×",
            TaskStatus.BLOCKED.value: "!",
            TaskStatus.PENDING.value: "○",
        }.get(task_state["status"], "?")
        route = task_state.get("route") or {}
        route_text = f" {route.get('level')}:{route.get('model')}" if route else ""
        failure = task_state.get("last_failure_type")
        failure_text = f" failure={failure}" if failure else ""
        print(
            f"{marker} {task_state.get('stage', 'default')}/{task_state.get('step', 'default')}/"
            f"{task_id}: {task_state['status']}{route_text} "
            f"(attempts={task_state['attempts']}{failure_text})"
        )
    return 0


def cmd_handoff(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    state = StateStore(root).ensure_for_plan(plan)
    path = HandoffWriter(root).write(plan, state)
    print(path.relative_to(root))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autodev", description="Dev Task Router V0.7")
    parser.add_argument("--root", help="project root; defaults to current directory")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="initialize .autodev files")
    init_parser.add_argument("--name", help="project name")
    init_parser.set_defaults(func=cmd_init)

    sub.add_parser("plan", help="validate and show routed tasks").set_defaults(func=cmd_plan)
    sub.add_parser("models", help="show model profiles").set_defaults(func=cmd_models)
    sub.add_parser("start", help="run pending tasks").set_defaults(func=cmd_start)
    sub.add_parser("pause", help="pause before the next task").set_defaults(func=cmd_pause)
    sub.add_parser("resume", help="resume a paused workflow").set_defaults(func=cmd_resume)
    sub.add_parser("handoff", help="regenerate handoff.md").set_defaults(func=cmd_handoff)

    repo_parser = sub.add_parser("repo-context", help="show or import verified repository context")
    repo_parser.add_argument("--import", dest="import_file", help="import YAML/JSON repository evidence")
    repo_parser.add_argument("--json", action="store_true", help="print raw context JSON")
    repo_parser.set_defaults(func=cmd_repo_context)

    context_parser = sub.add_parser("context", help="show or import rolling project context")
    context_parser.add_argument("--import", dest="import_file", help="import YAML/JSON rolling context")
    context_parser.add_argument("--json", action="store_true", help="print raw context JSON")
    context_parser.set_defaults(func=cmd_context)

    pack_parser = sub.add_parser("context-pack", help="build a budgeted context pack for one task")
    pack_parser.add_argument("task", help="task id")
    pack_parser.add_argument("--json", action="store_true", help="print context pack JSON")
    pack_parser.set_defaults(func=cmd_context_pack)

    retry_parser = sub.add_parser("retry", help="reset one FAILED/BLOCKED task")
    retry_parser.add_argument("task", help="task id")
    retry_parser.add_argument("--run", action="store_true", help="run workflow immediately after reset")
    retry_parser.set_defaults(func=cmd_retry)

    status_parser = sub.add_parser("status", help="show workflow state")
    status_parser.add_argument("--json", action="store_true", help="print raw state JSON")
    status_parser.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
