from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .executor import ExecutionRequest, ExecutorRegistry
from .models import TaskRole, TaskSpec
from .router import RuleRouter


@dataclass(frozen=True, slots=True)
class ReviewReport:
    ok: bool
    message: str
    raw: str = ""
    returncode: int | None = None


class Reviewer:
    def __init__(self, router: RuleRouter, registry: ExecutorRegistry):
        self.router = router
        self.registry = registry

    @staticmethod
    def _prompt(task: TaskSpec, checker_evidence: str) -> str:
        criteria = "\n".join(f"- {item}" for item in task.acceptance) or "- Task intent is satisfied"
        evidence = checker_evidence.strip() or "(no checker output)"
        original = task.prompt or task.title
        return (
            "You are an independent code reviewer. Do not modify files.\n"
            "Review the completed task against the acceptance criteria and checker evidence.\n"
            "Your final non-empty line MUST start with PASS or FAIL.\n\n"
            f"Task: {task.title}\n"
            f"Original instruction: {original}\n\n"
            f"Acceptance criteria:\n{criteria}\n\n"
            f"Checker evidence:\n{evidence}\n"
        )

    def review(self, task: TaskSpec, *, root: Path, checker_evidence: str) -> ReviewReport:
        route = self.router.decision_for_level(task.review_level, "independent reviewer")
        try:
            executor = self.registry.get(route.profile.executor)
        except ValueError as exc:
            return ReviewReport(False, str(exc))

        request = ExecutionRequest(
            task_id=f"{task.id}:review",
            command=None,
            prompt=self._prompt(task, checker_evidence),
            cwd=root,
            role=TaskRole.REVIEWER,
            route=route,
        )
        result = executor.run(request)
        raw = result.stdout.strip()
        if result.returncode != 0:
            return ReviewReport(
                False,
                result.stderr.strip() or f"reviewer exited {result.returncode}",
                raw,
                result.returncode,
            )

        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if not lines:
            return ReviewReport(False, "reviewer returned empty output", raw, result.returncode)
        verdict = lines[-1].upper()
        if verdict.startswith("PASS"):
            return ReviewReport(True, lines[-1], raw, result.returncode)
        if verdict.startswith("FAIL"):
            return ReviewReport(False, lines[-1], raw, result.returncode)
        return ReviewReport(
            False,
            "reviewer output must end with PASS or FAIL",
            raw,
            result.returncode,
        )
