from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import load_local_switch, load_plan, load_surfaces
from .conversation_response_ui import load_local_response_config
from .conversation_ui import load_local_conversation_config
from .e2e_calibration import EndToEndCalibrationRecorder
from .execution_audit import LocalExecutionAuditor
from .models import ModelLevel, Plan, TaskSpec
from .profile_calibration import ProfileCalibrationRegistry
from .ui_fingerprint import UIFingerprintStore


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    code: str
    scope: str
    status: str
    message: str

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "scope": self.scope,
            "status": self.status,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class V1ReadinessReport:
    automated_ready: bool
    live_windows_ready: bool
    release_ready: bool
    checks: tuple[ReadinessCheck, ...]

    def to_dict(self) -> dict:
        return {
            "automated_ready": self.automated_ready,
            "live_windows_ready": self.live_windows_ready,
            "release_ready": self.release_ready,
            "checks": [check.to_dict() for check in self.checks],
        }


class V1ReadinessEvaluator:
    """Evaluate V1.0 readiness without converting configuration into fake live proof."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    @staticmethod
    def _task_for_dispatch(
        plan: Plan | None,
        recorder: EndToEndCalibrationRecorder,
        dispatch_id: str,
    ) -> TaskSpec | None:
        if plan is None:
            return None
        events = recorder.evidence.events_for_dispatch(dispatch_id)
        task_ids = {event.task_id for event in events if event.task_id}
        if len(task_ids) != 1:
            return None
        task_id = next(iter(task_ids))
        for task in plan.tasks:
            if task.id == task_id:
                return task
        return None

    def run(self, *, current_ui_fingerprint: str | None = None) -> V1ReadinessReport:
        checks: list[ReadinessCheck] = []
        plan: Plan | None = None

        # Automated/read-only integrity. Parsing these files is useful because it catches
        # malformed plans/routes before the live Windows layer is involved.
        try:
            plan = load_plan(self.root)
            surfaces = load_surfaces(self.root)
            for level in (ModelLevel.LOW, ModelLevel.MEDIUM, ModelLevel.HIGH):
                decision = surfaces.route(level, "chat")
                if not decision.resolved:
                    raise ValueError(f"chat route unresolved for {level.value}")
            checks.append(
                ReadinessCheck(
                    "AUTOMATED_CORE_CONFIG",
                    "automated",
                    "PASS",
                    f"plan {plan.project!r} and LOW/MEDIUM/HIGH chat routes parse successfully",
                )
            )
        except (FileNotFoundError, ValueError) as exc:
            checks.append(
                ReadinessCheck(
                    "AUTOMATED_CORE_CONFIG",
                    "automated",
                    "BLOCKED",
                    f"core project/routing configuration is invalid: {exc}",
                )
            )

        try:
            audit = LocalExecutionAuditor(self.root).run()
            checks.append(
                ReadinessCheck(
                    "AUTOMATED_RUNTIME_AUDIT",
                    "automated",
                    "PASS" if audit.ok else "BLOCKED",
                    (
                        f"runtime evidence audit has {len(audit.errors)} error(s) and "
                        f"{len(audit.warnings)} warning(s)"
                    ),
                )
            )
        except (OSError, ValueError) as exc:
            checks.append(
                ReadinessCheck(
                    "AUTOMATED_RUNTIME_AUDIT",
                    "automated",
                    "BLOCKED",
                    f"runtime audit could not be completed: {exc}",
                )
            )

        # Local selector configuration is necessary but intentionally not sufficient
        # for live readiness.
        try:
            switch = load_local_switch(self.root)
            efforts_ok = all(switch.effort_labels.get(key) for key in ("low", "medium", "high"))
            verifies_ok = all(
                switch.verify_labels.get(key) or switch.effort_labels.get(key)
                for key in ("low", "medium", "high")
            )
            switch_configured = bool(
                switch.enabled and switch.selector_labels and efforts_ok and verifies_ok
            )
            checks.append(
                ReadinessCheck(
                    "WINDOWS_SWITCH_CONFIG",
                    "live_windows",
                    "PASS" if switch_configured else "PENDING",
                    (
                        "local exact switch configuration is populated"
                        if switch_configured
                        else "local exact switch configuration is still disabled or missing selector/effort labels"
                    ),
                )
            )
        except (OSError, ValueError) as exc:
            checks.append(
                ReadinessCheck(
                    "WINDOWS_SWITCH_CONFIG",
                    "live_windows",
                    "BLOCKED",
                    f"local switch configuration is invalid: {exc}",
                )
            )

        try:
            conversation = load_local_conversation_config(self.root)
            response = load_local_response_config(self.root)
            conversation_configured = bool(
                conversation.enabled
                and conversation.composer_labels
                and conversation.send_labels
                and response.enabled
                and response.assistant_automation_id_regex
            )
            checks.append(
                ReadinessCheck(
                    "WINDOWS_CONVERSATION_CONFIG",
                    "live_windows",
                    "PASS" if conversation_configured else "PENDING",
                    (
                        "composer/Send/response selectors are configured"
                        if conversation_configured
                        else "composer/Send/response selectors are still disabled or incomplete"
                    ),
                )
            )
        except (OSError, ValueError) as exc:
            checks.append(
                ReadinessCheck(
                    "WINDOWS_CONVERSATION_CONFIG",
                    "live_windows",
                    "BLOCKED",
                    f"local conversation configuration is invalid: {exc}",
                )
            )

        fingerprint_store = UIFingerprintStore(self.root)
        try:
            baseline = fingerprint_store.load()
        except (OSError, ValueError) as exc:
            baseline = None
            checks.append(
                ReadinessCheck(
                    "WINDOWS_UI_FINGERPRINT",
                    "live_windows",
                    "BLOCKED",
                    f"UI fingerprint baseline is invalid: {exc}",
                )
            )
        else:
            if baseline is None:
                checks.append(
                    ReadinessCheck(
                        "WINDOWS_UI_FINGERPRINT",
                        "live_windows",
                        "PENDING",
                        "no live Windows UI fingerprint baseline has been recorded",
                    )
                )
            elif not current_ui_fingerprint:
                checks.append(
                    ReadinessCheck(
                        "WINDOWS_UI_FINGERPRINT",
                        "live_windows",
                        "PENDING",
                        "a baseline exists but the current Windows UI has not been probed for this readiness run",
                    )
                )
            elif current_ui_fingerprint != baseline.digest:
                checks.append(
                    ReadinessCheck(
                        "WINDOWS_UI_FINGERPRINT",
                        "live_windows",
                        "BLOCKED",
                        "current UI fingerprint differs from the calibration baseline; selectors/profiles must be revalidated",
                    )
                )
            else:
                checks.append(
                    ReadinessCheck(
                        "WINDOWS_UI_FINGERPRINT",
                        "live_windows",
                        "PASS",
                        "current UI fingerprint matches the recorded calibration baseline",
                    )
                )

        registry = ProfileCalibrationRegistry(self.root)
        try:
            coverage = registry.coverage(current_ui_fingerprint)
            checks.append(
                ReadinessCheck(
                    "WINDOWS_PROFILE_SWITCH_CALIBRATION",
                    "live_windows",
                    "PASS" if coverage.switch_complete else "PENDING",
                    (
                        "LOW/MEDIUM/HIGH exact switches are verified for the current UI fingerprint"
                        if coverage.switch_complete
                        else (
                            "profile switch calibration incomplete or stale; "
                            f"missing={list(coverage.missing_levels)}, stale={list(coverage.stale_levels)}"
                        )
                    ),
                )
            )

            e2e_status = "PENDING"
            e2e_message = f"end-to-end verified levels={list(coverage.e2e_levels)}"
            if coverage.end_to_end_complete:
                recorder = EndToEndCalibrationRecorder(self.root, registry=registry)
                issues: list[str] = []
                records = registry.records()
                for level in registry.REQUIRED_LEVELS:
                    record = records.get(level)
                    if record is None or not record.evidence_dispatch_id:
                        issues.append(f"{level.value}: missing dispatch evidence id")
                        continue
                    task = self._task_for_dispatch(
                        plan,
                        recorder,
                        record.evidence_dispatch_id,
                    )
                    if task is None:
                        issues.append(f"{level.value}: dispatch does not map to exactly one planned task")
                        continue
                    ok, message = recorder.validate_record(task, record)
                    if not ok:
                        issues.append(f"{level.value}: {message}")
                if issues:
                    e2e_status = "BLOCKED"
                    e2e_message = "end-to-end calibration evidence is inconsistent: " + "; ".join(issues)
                else:
                    e2e_status = "PASS"
                    e2e_message = (
                        "LOW/MEDIUM/HIGH all have fingerprint-bound submitted/response/check/PASS evidence"
                    )
            checks.append(
                ReadinessCheck(
                    "WINDOWS_END_TO_END_CALIBRATION",
                    "live_windows",
                    e2e_status,
                    e2e_message,
                )
            )
        except (OSError, ValueError) as exc:
            checks.append(
                ReadinessCheck(
                    "WINDOWS_PROFILE_SWITCH_CALIBRATION",
                    "live_windows",
                    "BLOCKED",
                    f"profile calibration registry is invalid: {exc}",
                )
            )
            checks.append(
                ReadinessCheck(
                    "WINDOWS_END_TO_END_CALIBRATION",
                    "live_windows",
                    "BLOCKED",
                    "end-to-end calibration cannot be trusted while the profile/evidence registry is invalid",
                )
            )

        automated_checks = [check for check in checks if check.scope == "automated"]
        live_checks = [check for check in checks if check.scope == "live_windows"]
        automated_ready = bool(automated_checks) and all(check.passed for check in automated_checks)
        live_windows_ready = bool(live_checks) and all(check.passed for check in live_checks)
        return V1ReadinessReport(
            automated_ready=automated_ready,
            live_windows_ready=live_windows_ready,
            release_ready=automated_ready and live_windows_ready,
            checks=tuple(checks),
        )
