from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_plan, write_default_files
from .models import TaskStatus, WorkflowStatus
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
    print("initialized:")
    for path in paths:
        print(f"  {path.relative_to(root)}")
    print("  .autodev/state.json")
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    print(f"project: {plan.project}")
    for index, task in enumerate(plan.tasks, 1):
        print(f"{index}. [{task.model}] {task.id} - {task.title}")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    state = WorkflowEngine(root, plan, StateStore(root)).run()
    return 0 if state["status"] in {WorkflowStatus.PASSED.value, WorkflowStatus.PAUSED.value} else 1


def cmd_pause(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    store = StateStore(root)
    state = store.load()
    if state["status"] == WorkflowStatus.PASSED.value:
        print("workflow already passed")
        return 0
    state["status"] = WorkflowStatus.PAUSED.value
    store.save(state)
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
        print("workflow failed; V0.1 does not auto-retry failed tasks. Fix/reset state before resuming.")
        return 1
    state["status"] = WorkflowStatus.READY.value
    store.save(state)
    result = WorkflowEngine(root, plan, store).run()
    return 0 if result["status"] in {WorkflowStatus.PASSED.value, WorkflowStatus.PAUSED.value} else 1


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
        print(f"{marker} {task_id}: {task_state['status']} (attempts={task_state['attempts']})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="autodev", description="Dev Task Router V0.1")
    parser.add_argument("--root", help="project root; defaults to current directory")
    sub = parser.add_subparsers(dest="command", required=True)

    init_parser = sub.add_parser("init", help="initialize .autodev files")
    init_parser.add_argument("--name", help="project name")
    init_parser.set_defaults(func=cmd_init)

    plan_parser = sub.add_parser("plan", help="validate and show the current plan")
    plan_parser.set_defaults(func=cmd_plan)

    start_parser = sub.add_parser("start", help="run pending tasks")
    start_parser.set_defaults(func=cmd_start)

    pause_parser = sub.add_parser("pause", help="pause before the next task")
    pause_parser.set_defaults(func=cmd_pause)

    resume_parser = sub.add_parser("resume", help="resume a paused workflow")
    resume_parser.set_defaults(func=cmd_resume)

    status_parser = sub.add_parser("status", help="show workflow state")
    status_parser.add_argument("--json", action="store_true", help="print raw state JSON")
    status_parser.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
