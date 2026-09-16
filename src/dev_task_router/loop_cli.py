from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_local_switch, load_plan
from .local_loop import LocalConversationOrchestrator
from .mode_switch import DryRunModeSwitchBackend, WindowsUIAModeSwitchBackend
from .state import StateStore


def project_root(value: str | None) -> Path:
    return Path(value or ".").resolve()


def _orchestrator(root: Path, *, switch: bool, dry_run: bool = False) -> LocalConversationOrchestrator:
    plan = load_plan(root)
    store = StateStore(root)
    mode_backend = None
    if switch:
        if dry_run:
            mode_backend = DryRunModeSwitchBackend()
        else:
            config = load_local_switch(root)
            if config.backend == "dry-run":
                mode_backend = DryRunModeSwitchBackend()
            else:
                mode_backend = WindowsUIAModeSwitchBackend(config)
    return LocalConversationOrchestrator(
        root,
        plan,
        store,
        mode_backend=mode_backend,
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
    # A dry-run is inspection-only and should not fail a shell pipeline merely because
    # it intentionally cannot verify a real profile. Real switch gates fail closed.
    if args.dry_run:
        return 0
    return 0 if gate.allowed_to_dispatch or gate.blocker == "DETERMINISTIC" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autodev-local",
        description="Prepare and gate the next Task for the canonical local ChatGPT conversation",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "gate" and args.dry_run:
        args.switch = True
    try:
        return args.func(args)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
