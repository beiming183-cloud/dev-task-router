from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import load_local_switch, load_surfaces
from .live_calibration import LiveProfileCalibrator
from .mode_switch import (
    DryRunModeSwitchBackend,
    ModeSwitchController,
    WindowsUIAModeSwitchBackend,
)
from .models import ModelLevel


def project_root(value: str | None) -> Path:
    return Path(value or ".").resolve()


def _backend(root: Path, *, dry_run: bool = False):
    if dry_run:
        return DryRunModeSwitchBackend()
    config = load_local_switch(root)
    if config.backend == "dry-run":
        return DryRunModeSwitchBackend()
    return WindowsUIAModeSwitchBackend(config)


def cmd_probe(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    rows = _backend(root).probe()
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("no named accessibility controls found")
        return 0
    print("name\tcontrol_type\tautomation_id")
    for row in rows:
        print(f"{row['name']}\t{row['control_type']}\t{row['automation_id']}")
    return 0


def _switch_payload(result) -> dict:
    return {
        "requested": {
            "surface": result.requested.surface,
            "level": result.requested.level.value,
            "family": result.requested.family,
            "effort": result.requested.effort,
            "label": result.requested.label,
        },
        "actual": {
            "family": result.actual_family,
            "effort": result.actual_effort,
        },
        "verified": result.verified,
        "changed": result.changed,
        "backend": result.backend,
        "message": result.message,
    }


def cmd_switch(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    level = ModelLevel(args.level.upper())
    controller = ModeSwitchController(load_surfaces(root), _backend(root, dry_run=args.dry_run))
    result = controller.switch_level(level, args.surface)
    payload = _switch_payload(result)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        requested = payload["requested"]
        print(
            f"requested: {requested['surface']} {requested['family']}/"
            f"{requested['effort'] or 'default'} ({requested['level']})"
        )
        print(f"backend: {result.backend}")
        print(f"verified: {'yes' if result.verified else 'no'}")
        print(result.message)
    # Exact local mode refuses to report success if the selected profile cannot be verified.
    return 0 if result.verified or args.dry_run else 1


def cmd_calibrate_profile(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    level = ModelLevel(args.level.upper())
    fingerprint, record = LiveProfileCalibrator(root).calibrate(
        level,
        surface=args.surface,
    )
    payload = {
        "level": record.level.value,
        "family": record.family,
        "effort": record.effort,
        "switch_verified": record.switch_verified,
        "end_to_end_verified": record.end_to_end_verified,
        "ui_fingerprint": fingerprint.digest,
        "verified_at": record.verified_at,
        "registry": ".autodev/profile-calibration.json",
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"calibrated: {record.level.value} -> {record.family}/"
            f"{record.effort or 'default'}"
        )
        print(f"UI fingerprint: {fingerprint.digest}")
        print("exact switch verified: yes")
        print("end-to-end dispatch/response/check verification: pending")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="autodev-mode",
        description="Dev Task Router local exact ChatGPT mode switcher",
    )
    parser.add_argument("--root", help="project root; defaults to current directory")
    sub = parser.add_subparsers(dest="command", required=True)

    probe = sub.add_parser("probe", help="inspect named Windows UIA controls in ChatGPT")
    probe.add_argument("--json", action="store_true", help="print probe rows as JSON")
    probe.set_defaults(func=cmd_probe)

    switch = sub.add_parser("switch", help="switch the current ChatGPT UI to a routed profile")
    switch.add_argument("level", choices=["LOW", "MEDIUM", "HIGH", "low", "medium", "high"])
    switch.add_argument("--surface", default="chat", help="surface from .autodev/surfaces.yaml")
    switch.add_argument("--dry-run", action="store_true", help="resolve route but do not touch UI")
    switch.add_argument("--json", action="store_true", help="print result as JSON")
    switch.set_defaults(func=cmd_switch)

    calibrate = sub.add_parser(
        "calibrate-profile",
        help="perform a real exact switch and record verified profile calibration for the current UI fingerprint",
    )
    calibrate.add_argument(
        "level",
        choices=["LOW", "MEDIUM", "HIGH", "low", "medium", "high"],
    )
    calibrate.add_argument("--surface", default="chat")
    calibrate.add_argument("--json", action="store_true")
    calibrate.set_defaults(func=cmd_calibrate_profile)
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
