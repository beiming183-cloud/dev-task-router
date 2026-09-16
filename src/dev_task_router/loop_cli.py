from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_local_switch, load_plan
from .conversation_response_ui import (
    WindowsUIAResponseSnapshotSource,
    load_local_response_config,
)
from .conversation_ui import (
    WindowsUIAConversationBackend,
    load_local_conversation_config,
)
from .deterministic_runner import DeterministicTaskRunner
from .evidence_cycle import EvidenceTrackingCycle
from .execution_evidence import ExecutionEvidenceLedger
from .local_loop import DryRunConversationBackend, LocalConversationOrchestrator
from .local_project_loop import LocalProjectLoop
from .local_session import LocalTaskCycle
from .mode_switch import DryRunModeSwitchBackend, WindowsUIAModeSwitchBackend
from .recovery import LocalRecoveryController
from .response_monitor import ConversationResponseMonitor
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


def _cycle(root: Path) -> EvidenceTrackingCycle:
    plan = load_plan(root)
    store = StateStore(root)
    orchestrator = _orchestrator(root, switch=True, conversation=True)
    response_config = load_local_response_config(root)
    source = WindowsUIAResponseSnapshotSource(root, response_config)
    monitor = ConversationResponseMonitor(
        source,
        poll_interval_seconds=response_config.poll_interval_seconds,
        timeout_seconds=response_config.timeout_seconds,
        stable_polls=response_config.stable_polls,
    )
    base = LocalTaskCycle(root, plan, store, orchestrator, monitor)
    return EvidenceTrackingCycle(root, base)


def _project_loop(root: Path) -> LocalProjectLoop:
    cycle = _cycle(root)
    deterministic = DeterministicTaskRunner(
        root,
        cycle.plan,
        cycle.store,
        cycle.orchestrator.router,
    )
    return LocalProjectLoop(
        root,
        cycle.plan,
        cycle.store,
        cycle,
        deterministic_runner=deterministic,
    )


def _print_cycle(result, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    print(f"task: {result.task_id or 'none'}")
    print(f"status: {result.status}")
    print(f"dispatch: {result.dispatch_id or 'none'}")
    print(f"infrastructure failure: {'yes' if result.infrastructure_failure else 'no'}")
    print(result.message)
    if result.response is not None:
        print(f"response completed: {'yes' if result.response.completed else 'no'}")
        print(f"response polls: {result.response.polls}")
    if result.check is not None:
        print(f"checker: {'PASS' if result.check.ok else 'FAIL'}")


def _print_project_loop(result, *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    for index, item in enumerate(result.cycles, 1):
        print(
            f"{index}. {item.task_id or '-'}: {item.status} "
            f"dispatch={item.dispatch_id or '-'}"
        )
    print(f"stop: {result.stop_reason}")
    print(f"workflow: {result.workflow_status}")


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
            print("low-level dispatch only; response/checker state is not advanced")
        else:
            print(outcome.gate.message)
    if outcome.gate.blocker == "DETERMINISTIC":
        return 0
    return 0 if outcome.dispatched else 1


def cmd_run(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    result = _project_loop(root).run_one()
    _print_cycle(result, json_output=args.json)
    if result.status in {"PASSED", "REVIEW_REQUIRED", "NO_TASK"}:
        return 0
    return 1


def cmd_resume(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    loop = _project_loop(root)
    cycle = loop.cycle
    task = cycle.orchestrator.next_task()
    if task is None:
        payload = {
            "task_id": "",
            "status": "NO_TASK",
            "dispatch_id": None,
            "infrastructure_failure": False,
            "message": "workflow has no unresolved task",
            "response": None,
            "check": None,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print("workflow has no unresolved task")
        return 0
    if cycle.sessions.active_for_task(task.id) is None:
        payload = {
            "task_id": task.id,
            "status": "NO_ACTIVE_SESSION",
            "dispatch_id": None,
            "infrastructure_failure": True,
            "message": "resume refuses to create a new dispatch; use `autodev-local run` for a new Task send",
            "response": None,
            "check": None,
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"task: {task.id}")
            print("status: NO_ACTIVE_SESSION")
            print(payload["message"])
        return 1

    result = loop.run_one()
    _print_cycle(result, json_output=args.json)
    return 0 if result.status in {"PASSED", "REVIEW_REQUIRED"} else 1


def cmd_recover(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    cycle = _cycle(root)
    controller = LocalRecoveryController(root, cycle.cycle, evidence=cycle.evidence)
    result = controller.reconcile_next()
    if result.dispatch_id:
        cycle.sync_dispatch(result.dispatch_id)
    payload = result.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"task: {result.task_id or 'none'}")
        print(f"dispatch: {result.dispatch_id or 'none'}")
        print(f"status: {result.status}")
        print(f"safe to retry: {'yes' if result.safe_to_retry else 'no'}")
        print(f"resumable: {'yes' if result.resumable else 'no'}")
        print(result.message)
    return 0 if result.status in {"NO_TASK", "SAFE_RETRY", "RESUME", "ALREADY_RESUMABLE"} else 1


def cmd_evidence(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    ledger = ExecutionEvidenceLedger(root)
    events = (
        ledger.events_for_dispatch(args.dispatch_id)
        if args.dispatch_id
        else ledger.events()
    )
    payload = {
        "chain_valid": ledger.verify_chain(),
        "event_count": len(events),
        "events": [event.to_dict() for event in events],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"chain valid: {'yes' if payload['chain_valid'] else 'no'}")
        print(f"events: {payload['event_count']}")
        for event in events:
            print(
                f"{event.sequence}. {event.kind} task={event.task_id} "
                f"dispatch={event.dispatch_id or '-'}"
            )
    return 0 if payload["chain_valid"] else 1


def cmd_continue(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    result = _project_loop(root).run_until_blocked(max_cycles=args.max_cycles)
    _print_project_loop(result, json_output=args.json)
    if result.stop_reason in {"COMPLETE", "REVIEW_REQUIRED"}:
        return 0
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autodev-local",
        description=(
            "Prepare, gate, dispatch, collect, recover, and verify Tasks in the canonical local ChatGPT conversation"
        ),
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
        help="read visible ChatGPT UIA controls for composer/send/response calibration without clicking",
    )
    probe.add_argument("--json", action="store_true", help="print probe rows as JSON")
    probe.set_defaults(func=cmd_probe_conversation)

    dispatch = sub.add_parser(
        "dispatch",
        help="low-level one-shot submit after gate verification; does not collect or check response",
    )
    dispatch.add_argument("--json", action="store_true", help="print the dispatch result as JSON")
    dispatch.set_defaults(func=cmd_dispatch)

    run = sub.add_parser(
        "run",
        help="run one full Task cycle; deterministic NONE runs locally, model Tasks use the current conversation",
    )
    run.add_argument("--json", action="store_true", help="print the cycle result as JSON")
    run.set_defaults(func=cmd_run)

    resume = sub.add_parser(
        "resume",
        help="resume an existing submitted/waiting model Task only; never creates a new dispatch",
    )
    resume.add_argument("--json", action="store_true", help="print the cycle result as JSON")
    resume.set_defaults(func=cmd_resume)

    recover = sub.add_parser(
        "recover",
        help="reconcile a PREPARED/ambiguous local send using durable dispatch and calibrated response evidence",
    )
    recover.add_argument("--json", action="store_true", help="print the recovery result as JSON")
    recover.set_defaults(func=cmd_recover)

    evidence = sub.add_parser(
        "evidence",
        help="inspect and verify the compact append-only local execution evidence chain",
    )
    evidence.add_argument("--dispatch-id", help="show events for one dispatch only")
    evidence.add_argument("--json", action="store_true", help="print evidence as JSON")
    evidence.set_defaults(func=cmd_evidence)

    continuous = sub.add_parser(
        "continue",
        help="continue across verified Tasks/retries/NONE commands until blocked, complete, or the cycle guard is reached",
    )
    continuous.add_argument(
        "--max-cycles",
        type=int,
        default=10,
        help="maximum Task execution cycles in this invocation (default: 10)",
    )
    continuous.add_argument("--json", action="store_true", help="print the project loop result as JSON")
    continuous.set_defaults(func=cmd_continue)
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
