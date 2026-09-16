from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import autodev_dir


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    event_id: str
    sequence: int
    task_id: str
    dispatch_id: str | None
    kind: str
    at: str
    data: dict[str, Any]
    previous_hash: str
    record_hash: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExecutionEvidence":
        if not isinstance(data, dict):
            raise ValueError("execution evidence row must be a mapping")
        payload = data.get("data", {})
        if not isinstance(payload, dict):
            raise ValueError("execution evidence data must be a mapping")
        return cls(
            event_id=str(data.get("event_id", "")),
            sequence=int(data.get("sequence", 0)),
            task_id=str(data.get("task_id", "")),
            dispatch_id=(
                str(data["dispatch_id"])
                if data.get("dispatch_id") not in (None, "")
                else None
            ),
            kind=str(data.get("kind", "")),
            at=str(data.get("at", "")),
            data=payload,
            previous_hash=str(data.get("previous_hash", "")),
            record_hash=str(data.get("record_hash", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "task_id": self.task_id,
            "dispatch_id": self.dispatch_id,
            "kind": self.kind,
            "at": self.at,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "record_hash": self.record_hash,
        }


class ExecutionEvidenceLedger:
    """Compact append-only evidence for local execution and crash recovery.

    Events store hashes/status metadata, not full conversation history. Recording is
    idempotent by semantic event_id, so replaying a recovery boundary does not append
    duplicate audit rows.
    """

    def __init__(self, root: Path):
        self.path = autodev_dir(root) / "execution-evidence.jsonl"

    def events(self) -> tuple[ExecutionEvidence, ...]:
        if not self.path.exists():
            return ()
        rows: list[ExecutionEvidence] = []
        for line_number, raw in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not raw.strip():
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"execution evidence line {line_number} is invalid JSON"
                ) from exc
            rows.append(ExecutionEvidence.from_dict(parsed))
        return tuple(rows)

    @staticmethod
    def _event_id(
        task_id: str,
        dispatch_id: str | None,
        kind: str,
        data: dict[str, Any],
    ) -> str:
        semantic = {
            "task_id": task_id,
            "dispatch_id": dispatch_id,
            "kind": kind,
            "data": data,
        }
        return hashlib.sha256(_canonical(semantic).encode("utf-8")).hexdigest()

    @staticmethod
    def _record_hash(body: dict[str, Any]) -> str:
        return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()

    def record(
        self,
        *,
        task_id: str,
        kind: str,
        dispatch_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> ExecutionEvidence:
        task_id = task_id.strip()
        kind = kind.strip().upper()
        if not task_id:
            raise ValueError("execution evidence task_id cannot be empty")
        if not kind:
            raise ValueError("execution evidence kind cannot be empty")
        payload = dict(data or {})
        event_id = self._event_id(task_id, dispatch_id, kind, payload)
        existing = self.events()
        for event in existing:
            if event.event_id == event_id:
                return event

        sequence = len(existing) + 1
        previous_hash = existing[-1].record_hash if existing else ""
        body = {
            "event_id": event_id,
            "sequence": sequence,
            "task_id": task_id,
            "dispatch_id": dispatch_id,
            "kind": kind,
            "at": _now_iso(),
            "data": payload,
            "previous_hash": previous_hash,
        }
        record_hash = self._record_hash(body)
        event = ExecutionEvidence(record_hash=record_hash, **body)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False, sort_keys=True) + "\n")
        return event

    def events_for_dispatch(self, dispatch_id: str) -> tuple[ExecutionEvidence, ...]:
        return tuple(event for event in self.events() if event.dispatch_id == dispatch_id)

    def latest_for_dispatch(self, dispatch_id: str) -> ExecutionEvidence | None:
        events = self.events_for_dispatch(dispatch_id)
        return events[-1] if events else None

    def verify_chain(self) -> bool:
        previous_hash = ""
        for expected_sequence, event in enumerate(self.events(), 1):
            if event.sequence != expected_sequence:
                return False
            if event.previous_hash != previous_hash:
                return False
            body = event.to_dict()
            actual_hash = body.pop("record_hash")
            if self._record_hash(body) != actual_hash:
                return False
            previous_hash = event.record_hash
        return True
