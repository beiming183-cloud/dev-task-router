from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .calibration import OutcomeCalibrator
from .config import load_local_switch, load_plan
from .conversation_response_ui import load_local_response_config
from .conversation_ui import WindowsUIAConversationBackend, load_local_conversation_config
from .debug_task import DebugTaskMaterializer
from .mode_switch import WindowsUIAModeSwitchBackend
from .state import StateStore
from .ui_fingerprint import UIFingerprint, UIFingerprintStore


def project_root(value: str | None) -> Path:
    return Path(value or ".").resolve()


def _tracked_labels(root: Path) -> dict[str, tuple[str, ...]]:
    mode = load_local_switch(root)
    conversation = load_local_conversation_config(root)
    response = load_local_response_config(root)
    tracked: dict[str, tuple[str, ...]] = {
        "mode.selector": mode.selector_labels,
        "conversation.composer": conversation.composer_labels,
        "conversation.send": conversation.send_labels,
        "response.busy": response.busy_labels,
    }
    for prefix, mapping in (
        ("mode.family", mode.family_labels),
        ("mode.effort", mode.effort_labels),
        ("mode.verify", mode.verify_labels),
    ):
        for key, labels in mapping.items():
            tracked[f"{prefix}.{key}"] = labels
    return {key: value for key, value in tracked.items() if value}


def _fingerprint(root: Path) -> UIFingerprint:
    mode_config = load_local_switch(root)
    conversation_config = load_local_conversation_config(root)
    mode_rows = WindowsUIAModeSwitchBackend(mode_config).probe()
    conversation_rows = WindowsUIAConversationBackend(root, conversation_config).probe()
    return UIFingerprint.from_rows(
        {"mode": mode_rows, "conversation": conversation_rows},
        tracked_labels=_tracked_labels(root),
    )


def cmd_fingerprint(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    current = _fingerprint(root)
    store = UIFingerprintStore(root)
    comparison = store.compare(current)
    if args.record:
        if current.stable_control_count < 1:
            raise RuntimeError("refusing to record an empty/unstable UI fingerprint")
        store.save(current)
        comparison = store.compare(current)
    payload = {
        "current": current.to_dict(),
        "comparison": comparison.to_dict(),
        "baseline_path": store.path.relative_to(root).as_posix(),
        "recorded": bool(args.record),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"UI fingerprint: {comparison.status}")
        print(f"digest: {current.digest}")
        print(f"stable controls: {current.stable_control_count}")
        print(f"total controls: {current.control_count}")
        for reason in comparison.reasons:
            print(f"- {reason}")
        if args.record:
            print(f"baseline recorded: {payload['baseline_path']}")
    return 1 if comparison.drifted else 0


def _debug_source_task(root: Path, requested: str | None) -> str:
    plan = load_plan(root)
    state = StateStore(root).ensure_for_plan(plan)
    if requested:
        if requested not in state["tasks"]:
            raise ValueError(f"unknown task: {requested}")
        return requested
    candidates = [
        task.id
        for task in plan.tasks
        if state["tasks"][task.id].get("debug_task_required")
    ]
    if not candidates:
        raise ValueError("no task currently requires debug-task materialization")
    if len(candidates) > 1:
        raise ValueError(
            "multiple tasks require debugging; pass --task-id explicitly: "
            + ", ".join(candidates)
        )
    return candidates[0]


def cmd_debug_task(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    store = StateStore(root)
    task_id = _debug_source_task(root, args.task_id)
    candidate = DebugTaskMaterializer(root, plan, store).materialize(task_id)
    payload = candidate.to_dict()
    payload["path"] = candidate.path.relative_to(root).as_posix()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"source task: {candidate.source_task_id}")
        print(f"debug task: {candidate.debug_task_id}")
        print(f"candidate: {payload['path']}")
        print("level is intentionally unset; classify this debug Task independently")
    return 0


def cmd_calibration(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    plan = load_plan(root)
    report = OutcomeCalibrator(root, plan, StateStore(root)).run()
    payload = report.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"observed tasks: {report.observed_task_count}/{report.task_count}")
        print(f"promotions: {report.promotion_count}")
        print(f"HIGH first-route tasks: {report.high_first_route_count}")
        print(f"HIGH after promotion: {report.high_after_promotion_count}")
        print(f"usage records: {report.usage_record_count}")
        print(f"token-bearing records: {report.token_record_count}")
        print(
            "calibration is descriptive only; routing thresholds are not changed automatically"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autodev-readiness",
        description="V1.0 readiness diagnostics for UI drift, debug-task materialization, and routing outcomes",
    )
    parser.add_argument("--root", help="project root; defaults to current directory")
    sub = parser.add_subparsers(dest="command", required=True)

    fingerprint = sub.add_parser(
        "fingerprint",
        help="probe privacy-safe Windows UI structure and compare it with the recorded baseline",
    )
    fingerprint.add_argument(
        "--record",
        action="store_true",
        help="record the current UI fingerprint as the calibration baseline",
    )
    fingerprint.add_argument("--json", action="store_true")
    fingerprint.set_defaults(func=cmd_fingerprint)

    debug = sub.add_parser(
        "debug-task",
        help="materialize a separate independently-classified debug Task from deterministic failure evidence",
    )
    debug.add_argument("--task-id")
    debug.add_argument("--json", action="store_true")
    debug.set_defaults(func=cmd_debug_task)

    calibration = sub.add_parser(
        "calibration",
        help="summarize predicted routing levels and observed outcomes without changing policy",
    )
    calibration.add_argument("--json", action="store_true")
    calibration.set_defaults(func=cmd_calibration)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
