from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_local_switch, load_plan
from .conversation_ui import (
    WindowsUIAConversationBackend,
    load_local_conversation_config,
)
from .local_loop import DryRunConversationBackend, LocalConversationOrchestrator
from .mode_switch import DryRunModeSwitchBackend, WindowsUIAModeSwitchBackend
from .state import StateStore


def project_root(value: str | None) -> Path:
    return Path(value or ".").resolve()


def _mode_backend(root: Path, *, dry_run: bool = False):
    if dry_run:
        return DryRunModeSwitchBackend()
    config = load_local_switch(root)
    if config.backend == "dry-run":
        return DryRunModeSwitchBackend()
    return WindowsUIAModeSwitchBackend(config)


def _conversation_backend(root: Path):
    config = load_local_conversation_config(root)
    if config.backend == "dry-run":
        return DryRunConversationBackend()
    return WindowsUIAConversationBackend(root, config)


def _orchestrator(
    root: Path,
    *,
    switch: bool,
    dry_run: bool = False,
    conversation: bool = False,
) -> LocalConversationOrchestrator:
    plan = load_plan(root)
    store = StateStore(root)
    mode_backend = _mode_backend(root, dry_run=dry_run) if switch else None
    conversation_backend = _conversation_backend(root) if conversation else None
    return LocalConversationOrchestrator(
        root,
        plan,
        store,
        mode_backend=mode_backend,
        conversation_backend=conversation_backend,
    )


def cmd_prepare(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    orchestrator = _orchestrator(root, switch=False)
    envelope = orchestrator.prepare()
    payload = envelope.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        profile = payload["requested_profile"] or {}
        print(f"task: {payload['task_id']}")
        print(f"difficulty: {payload['difficulty']}")
        print(f"deterministic: {'yes' if payload['deterministic'] else 'no'}")
        if profile:
            print(
                f"requested: {profile['surface']} {profile['family']}/"
                f"{profile['effort'] or 'default'}"
            )
        print(f"stale context: {'yes' if payload['context_pack']['stale_context'] else 'no'}")
        print("prepared only; no ChatGPT UI action was performed")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    orchestrator = _orchestrator(root, switch=args.switch, dry_run=args.dry_run)
    envelope = orchestrator.prepare()
    gate = orchestrator.gate(envelope)
    payload = gate.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"task: {envelope.task_id}")
        print(f"difficulty: {envelope.difficulty.value}")
        print(f"allowed to dispatch: {'yes' if gate.allowed_to_dispatch else 'no'}")
        print(f"blocker: {gate.blocker or 'none'}")
        if gate.switch_result is not None:
            print(f"switch backend: {gate.switch_result.backend}")
            print(f"switch verified: {'yes' if gate.switch_result.verified else 'no'}")
        print(gate.message)
    if args.dry_run:
        return 0
    return 0 if gate.allowed_to_dispatch or gate.blocker == "DETERMINISTIC" else 1


def cmd_probe_conversation(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    config = load_local_conversation_config(root)
    backend = WindowsUIAConversationBackend(root, config)
    rows = backend.probe()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(
                f"{row['control_type'] or '-'}\t{row['automation_id'] or '-'}\t{row['name'] or '-'}"
            )
    return 0


def cmd_dispatch(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    orchestrator = _orchestrator(root, switch=True, conversation=True)
    outcome = orchestrator.dispatch()
    payload = outcome.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"task: {outcome.gate.envelope.task_id}")
        print(f"gate: {'open' if outcome.gate.allowed_to_dispatch else 'closed'}")
        print(f"blocker: {outcome.gate.blocker or 'none'}")
        print(f"dispatched: {'yes' if outcome.dispatched else 'no'}")
        if outcome.dispatch is not None:
            print(outcome.dispatch.message)
        else:
            print(outcome.gate.message)
    if outcome.gate.blocker == "DETERMINISTIC":
        return 0
    return 0 if outcome.dispatched else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autodev-local",
        description="Prepare, gate, and safely dispatch the next Task in the canonical local ChatGPT conversation",
    )
    parser.add_argument("--root", help="project root; defaults to current directory")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="build the next Task envelope without touching ChatGPT UI")
    prepare.add_argument("--json", action="store_true", help="print the full envelope as JSON")
    prepare.set_defaults(func=cmd_prepare)

    gate = sub.add_parser("gate", help="check whether the next Task may enter the ChatGPT conversation")
    gate.add_argument(
        "--switch",
        action="store_true",
        help="attempt the configured exact local mode switch before opening the gate",
    )
    gate.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve the switch path without touching ChatGPT UI",
    )
    gate.add_argument("--json", action="store_true", help="print the full gate result as JSON")
    gate.set_defaults(func=cmd_gate)

    probe = sub.add_parser(
        "probe-conversation",
        help="read visible ChatGPT UIA controls for composer/send calibration without clicking",
    )
    probe.add_argument("--json", action="store_true", help="print probe rows as JSON")
    probe.set_defaults(func=cmd_probe_conversation)

    dispatch = sub.add_parser(
        "dispatch",
        help="after calibration, verify mode gate and submit exactly one prepared Task to the current conversation",
    )
    dispatch.add_argument("--json", action="store_true", help="print the dispatch result as JSON")
    dispatch.set_defaults(func=cmd_dispatch)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "gate" and args.dry_run:
        args.switch = True
    try:
        return args.func(args)
    except (FileNotFoundError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
