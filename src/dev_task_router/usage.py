from __future__ import annotations

import json
from pathlib import Path

from .config import USAGE_FILE, autodev_dir
from .state import now_iso


class UsageLogger:
    def __init__(self, root: Path):
        self.path = autodev_dir(root) / USAGE_FILE

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
    ) -> None:
        record = {
            "timestamp": now_iso(),
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
            "input_tokens": None,
            "output_tokens": None,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
