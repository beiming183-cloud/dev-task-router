from __future__ import annotations

import json
from pathlib import Path

from .config import USAGE_FILE, autodev_dir
from .state import now_iso


class UsageLogger:
    """Append compact execution-usage evidence without inventing unavailable metrics.

    Token fields stay null unless an execution backend reports them. `usage_id` makes
    crash/recovery replay idempotent for callers that have a durable execution key.
    """

    def __init__(self, root: Path):
        self.path = autodev_dir(root) / USAGE_FILE

    def _has_usage_id(self, usage_id: str) -> bool:
        if not usage_id or not self.path.exists():
            return False
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("usage_id") == usage_id:
                return True
        return False

    def append(
        self,
        *,
        task_id: str,
        route: dict,
        status: str,
        returncode: int | None,
        attempt: int | None = None,
        phase: str = "EXECUTE",
        failure_type: str | None = None,
        duration_seconds: float | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        dispatch_id: str | None = None,
        source: str | None = None,
        usage_id: str | None = None,
    ) -> bool:
        if usage_id and self._has_usage_id(usage_id):
            return False
        duration = None
        if duration_seconds is not None:
            duration = max(0.0, float(duration_seconds))
        for name, value in (("input_tokens", input_tokens), ("output_tokens", output_tokens)):
            if value is not None and (not isinstance(value, int) or value < 0):
                raise ValueError(f"{name} must be a non-negative integer when provided")
        record = {
            "timestamp": now_iso(),
            "usage_id": usage_id,
            "task_id": task_id,
            "attempt": attempt,
            "phase": phase,
            "level": route.get("level"),
            "provider": route.get("provider"),
            "model": route.get("model"),
            "executor": route.get("executor"),
            "route_reason": route.get("reason"),
            "status": status,
            "failure_type": failure_type,
            "returncode": returncode,
            "duration_seconds": duration,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "dispatch_id": dispatch_id,
            "source": source,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
