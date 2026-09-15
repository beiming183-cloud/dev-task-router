from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class CommandExecutor:
    """V0.1 single executor: run an argv command without shell expansion."""

    def run(self, command: list[str], cwd: Path) -> CommandResult:
        completed = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return CommandResult(
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
