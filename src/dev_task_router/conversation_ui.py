from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LOCAL_CONVERSATION_FILE, autodev_dir, load_local_conversation_dict
from .local_loop import ConversationDispatchResult, LocalExecutionEnvelope


@dataclass(frozen=True, slots=True)
class LocalConversationConfig:
    enabled: bool
    backend: str
    window_title_regex: str
    composer_labels: tuple[str, ...]
    composer_control_types: tuple[str, ...]
    send_labels: tuple[str, ...]
    send_control_types: tuple[str, ...]
    max_prompt_chars: int

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LocalConversationConfig":
        if not isinstance(data, dict):
            raise ValueError("local conversation config must be a mapping")
        backend = str(data.get("backend", "windows-uia")).strip().lower()
        if backend not in {"windows-uia", "dry-run"}:
            raise ValueError("local conversation backend must be windows-uia or dry-run")

        window = data.get("window", {})
        composer = data.get("composer", {})
        send = data.get("send", {})
        limits = data.get("limits", {})
        for name, value in (
            ("window", window),
            ("composer", composer),
            ("send", send),
            ("limits", limits),
        ):
            if not isinstance(value, dict):
                raise ValueError(f"local conversation {name} must be a mapping")

        title_regex = str(window.get("title_regex", ".*ChatGPT.*")).strip()
        try:
            re.compile(title_regex)
        except re.error as exc:
            raise ValueError(f"invalid local conversation title_regex: {exc}") from exc

        def strings(value: Any, name: str) -> tuple[str, ...]:
            if value is None:
                return ()
            if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                raise ValueError(f"local conversation {name} must be a string list")
            return tuple(item.strip() for item in value if item.strip())

        max_prompt_chars = int(limits.get("max_prompt_chars", 60000))
        if max_prompt_chars <= 0:
            raise ValueError("local conversation max_prompt_chars must be > 0")

        return cls(
            enabled=bool(data.get("enabled", False)),
            backend=backend,
            window_title_regex=title_regex,
            composer_labels=strings(composer.get("labels"), "composer.labels"),
            composer_control_types=strings(
                composer.get("control_types", ["Edit", "Document"]),
                "composer.control_types",
            ),
            send_labels=strings(send.get("labels"), "send.labels"),
            send_control_types=strings(send.get("control_types", ["Button"]), "send.control_types"),
            max_prompt_chars=max_prompt_chars,
        )


def load_local_conversation_config(root: Path) -> LocalConversationConfig:
    return LocalConversationConfig.from_dict(load_local_conversation_dict(root))


def _norm(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _matches(text: str, labels: tuple[str, ...]) -> bool:
    value = _norm(text)
    return any(_norm(label) == value or _norm(label) in value for label in labels)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DispatchLedger:
    """Conservative duplicate-send guard.

    `submitting` is intentionally sticky. If the process crashes around the click,
    the next run blocks instead of risking a duplicate message. A future recovery
    command can reconcile the UI and ledger explicitly.
    """

    def __init__(self, root: Path):
        self.path = autodev_dir(root) / "local-dispatch.json"

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "entries": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("entries"), dict):
            raise ValueError("local-dispatch.json must contain an entries mapping")
        return data

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def get(self, dispatch_id: str) -> dict[str, Any] | None:
        return self._load()["entries"].get(dispatch_id)

    def ensure_available(self, dispatch_id: str) -> None:
        existing = self.get(dispatch_id)
        if existing and existing.get("status") in {"submitting", "submitted"}:
            raise RuntimeError(
                f"duplicate dispatch blocked: {dispatch_id} is already {existing.get('status')}"
            )

    def reserve(self, dispatch_id: str, task_id: str) -> None:
        data = self._load()
        existing = data["entries"].get(dispatch_id)
        if existing and existing.get("status") in {"submitting", "submitted"}:
            raise RuntimeError(
                f"duplicate dispatch blocked: {dispatch_id} is already {existing.get('status')}"
            )
        data["entries"][dispatch_id] = {
            "task_id": task_id,
            "status": "submitting",
            "updated_at": _now_iso(),
        }
        self._save(data)

    def mark_submitted(self, dispatch_id: str) -> None:
        data = self._load()
        entry = data["entries"].get(dispatch_id)
        if not entry:
            raise RuntimeError(f"dispatch ledger entry disappeared: {dispatch_id}")
        entry["status"] = "submitted"
        entry["updated_at"] = _now_iso()
        self._save(data)


class WindowsUIAConversationBackend:
    """Config-driven sender for the *current* visible ChatGPT conversation.

    This backend does not choose another chat and never uses fixed coordinates.
    It verifies the complete inserted prompt before clicking Send. Successful
    submission only means the UI accepted the message; it is not Task completion.
    """

    name = "windows-uia-conversation"

    def __init__(self, root: Path, config: LocalConversationConfig):
        self.root = root
        self.config = config
        self.ledger = DispatchLedger(root)

    @staticmethod
    def _desktop():
        if sys.platform != "win32":
            raise RuntimeError("windows-uia conversation backend requires Windows")
        try:
            from pywinauto import Desktop
        except ImportError as exc:
            raise RuntimeError(
                "windows-uia conversation backend requires: pip install -e '.[local]'"
            ) from exc
        return Desktop(backend="uia")

    def _window(self):
        windows = self._desktop().windows(
            title_re=self.config.window_title_regex,
            visible_only=True,
        )
        if not windows:
            raise RuntimeError(
                f"no visible window matches {self.config.window_title_regex!r}; open the canonical ChatGPT conversation first"
            )
        return windows[0]

    @staticmethod
    def _name(control) -> str:
        try:
            return (control.window_text() or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _control_type(control) -> str:
        try:
            return str(control.element_info.control_type or "")
        except Exception:
            return ""

    def _controls(self) -> list:
        window = self._window()
        return [window, *window.descendants()]

    def probe(self) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for control in self._controls():
            name = self._name(control)
            control_type = self._control_type(control)
            try:
                automation_id = str(control.element_info.automation_id or "")
            except Exception:
                automation_id = ""
            if not name and not automation_id:
                continue
            key = (name, control_type, automation_id)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "name": name,
                    "control_type": control_type,
                    "automation_id": automation_id,
                }
            )
        return rows

    def _find(
        self,
        labels: tuple[str, ...],
        control_types: tuple[str, ...],
        *,
        controls: list | None = None,
    ):
        if not labels:
            return None
        allowed = {_norm(item) for item in control_types}
        for control in controls or self._controls():
            if allowed and _norm(self._control_type(control)) not in allowed:
                continue
            if _matches(self._name(control), labels):
                return control
        return None

    @staticmethod
    def _read_value(control) -> str | None:
        for method_name in ("get_value", "window_text"):
            method = getattr(control, method_name, None)
            if callable(method):
                try:
                    value = method()
                except Exception:
                    continue
                if value is not None:
                    return str(value)
        try:
            props = control.legacy_properties()
            value = props.get("Value")
            if value is not None:
                return str(value)
        except Exception:
            pass
        return None

    @staticmethod
    def _set_value(control, text: str) -> None:
        errors: list[str] = []
        for method_name in ("set_edit_text", "set_value"):
            method = getattr(control, method_name, None)
            if not callable(method):
                continue
            try:
                method(text)
                return
            except Exception as exc:
                errors.append(f"{method_name}: {exc}")
        detail = "; ".join(errors) if errors else "no supported UIA value setter"
        raise RuntimeError(f"could not set ChatGPT composer text through UIA: {detail}")

    @staticmethod
    def _click(control) -> None:
        try:
            control.invoke()
            return
        except Exception:
            pass
        try:
            control.click_input()
            return
        except Exception as exc:
            raise RuntimeError("matched ChatGPT send control could not be invoked") from exc

    @staticmethod
    def dispatch_id(envelope: LocalExecutionEnvelope) -> str:
        profile = envelope.requested_profile
        profile_text = "none"
        if profile is not None:
            profile_text = f"{profile.surface}:{profile.family}:{profile.effort or 'default'}"
        payload = f"{envelope.task_id}\n{profile_text}\n{envelope.prompt_text()}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def dispatch(self, envelope: LocalExecutionEnvelope) -> ConversationDispatchResult:
        if not self.config.enabled:
            raise RuntimeError(
                f"local conversation dispatch is disabled; probe and calibrate {LOCAL_CONVERSATION_FILE} first"
            )
        if not self.config.composer_labels:
            raise RuntimeError("composer.labels is empty; probe and calibrate local conversation UI first")
        if not self.config.send_labels:
            raise RuntimeError("send.labels is empty; probe and calibrate local conversation UI first")

        prompt = envelope.prompt_text()
        if not prompt:
            raise RuntimeError("refusing to dispatch an empty/deterministic conversation prompt")
        if len(prompt) > self.config.max_prompt_chars:
            raise RuntimeError(
                f"context pack is {len(prompt)} chars, above local conversation limit {self.config.max_prompt_chars}"
            )

        dispatch_id = self.dispatch_id(envelope)
        # Duplicate protection must run before touching the UI. A prior submitted or
        # ambiguous `submitting` record wins even if the composer is currently absent.
        self.ledger.ensure_available(dispatch_id)

        controls = self._controls()
        composer = self._find(
            self.config.composer_labels,
            self.config.composer_control_types,
            controls=controls,
        )
        if composer is None:
            raise RuntimeError("configured ChatGPT composer control was not found")

        self._set_value(composer, prompt)
        actual = self._read_value(composer)
        if actual is None:
            raise RuntimeError("composer text was set but could not be read back for verification")
        normalize_newlines = lambda value: value.replace("\r\n", "\n").strip()
        if normalize_newlines(actual) != normalize_newlines(prompt):
            raise RuntimeError("composer read-back does not match the prepared Task Context Pack")

        # Filling the composer can change which Send control is visible/enabled.
        send_control = self._find(
            self.config.send_labels,
            self.config.send_control_types,
            controls=self._controls(),
        )
        if send_control is None:
            raise RuntimeError("configured ChatGPT send control was not found after composer verification")

        # Reservation happens only after the complete prompt has been read back. That
        # avoids permanently locking a task because of a harmless pre-send UI failure.
        self.ledger.reserve(dispatch_id, envelope.task_id)
        # If this click is ambiguous or the process crashes, the sticky `submitting`
        # record prevents an automatic second send.
        self._click(send_control)
        self.ledger.mark_submitted(dispatch_id)
        return ConversationDispatchResult(
            accepted=True,
            backend=self.name,
            message=f"submitted to current canonical conversation; dispatch_id={dispatch_id}",
            response_text="",
        )
