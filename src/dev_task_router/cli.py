from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from .config import load_models, load_plan, write_default_files
from .handoff import HandoffWriter
from .models import TaskStatus, WorkflowStatus
from .router import RuleRouter
from .state import StateStore
from .workflow import WorkflowEngine


def project_root(value: str | None) -> Path:
    return Path(value or ".").resolve()


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
    router = RuleRouter(load_models(root))
    print(f"project: {plan.project}")
    for index, task in enumerate(plan.tasks, 1):
        route = router.route(task)
        print(
            f"{index}. {task.stage_id}/{task.step_id} [{task.role.value}/{route.level.value}] "
            f"{task.id} - {task.title} -> {route.profile.provider}:{route.profile.model} "
            f"via {route.profile.executor} ({route.reason})"
        )
    return 0


def cmd_models(args: argparse.Namespace) -> int:
    catalog = load_models(project_root(args.root))
    for level, profile in catalog.profiles.items():
        print(f"{level.value}: {profile.provider}:{profile.model} via {profile.executor}")
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
    if state["status"] == WorkflowStatus.FAILED.value:
        print("workflow failed; V0.2 does not auto-retry failed tasks")
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
    if state["status"] == WorkflowStatus.FAILED.value:
        print("workflow failed; a failed workflow cannot be paused")
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
    if state["status"] == WorkflowStatus.FAILED.value:
        print("workflow failed; V0.2 does not auto-retry failed tasks. Fix/reset state before resuming.")
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
            TaskStatus.PENDING.value: "○",
        }.get(task_state["status"], "?")
        route = task_state.get("route") or {}
        route_text = f" {route.get('level')}:{route.get('model')}" if route else ""
        print(
            f"{marker} {task_state.get('stage', 'default')}/{task_state.get('step', 'default')}/"
            f"{task_id}: {task_state['status']}{route_text} (attempts={task_state['attempts']})"
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
    parser = argparse.ArgumentParser(prog="autodev", description="Dev Task Router V0.2")
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
