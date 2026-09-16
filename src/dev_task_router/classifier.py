from __future__ import annotations

from dataclasses import dataclass

from .models import ModelLevel, TaskRole, TaskSpec


@dataclass(frozen=True, slots=True)
class DifficultyAssessment:
    level: ModelLevel
    score: int
    confidence: str
    reason: str
    factors: tuple[str, ...]
    traits: tuple[str, ...]


_KIND_BASE = {
    "test": 0,
    "build": 0,
    "repo_search": 1,
    "docs": 1,
    "handoff": 1,
    "simple_edit": 1,
    "normal_code": 4,
    "normal_debug": 4,
    "architecture": 8,
    "planning": 8,
    "complex_code": 8,
    "hard_debug": 8,
    "review": 8,
}

_LOW_HINTS = (
    "rename", "label", "copy text", "string", "comment", "docs", "documentation",
    "format", "formatter", "locate", "find file", "search symbol", "handoff",
    "重命名", "文档", "字符串", "标签", "注释", "格式化", "查找文件", "搜索符号",
)
_MEDIUM_HINTS = (
    "feature", "bug", "refactor", "api integration", "multiple files", "multi-file",
    "unit test", "integration test", "ordinary implementation", "normal implementation",
    "功能", "常规 bug", "普通 bug", "重构", "接口集成", "多文件", "单元测试", "集成测试",
)
_ARCH_HINTS = (
    "architecture", "architectural", "state machine", "core semantics", "semantic cursor",
    "semantic selection", "compiler", "parser architecture", "protocol design",
    "架构", "状态机", "核心语义", "语义光标", "语义选区", "编译器", "解析器架构", "协议设计",
)
_STATE_HINTS = (
    "concurrency", "concurrent", "transaction", "persistence", "lifecycle", "history",
    "selection state", "stateful", "race condition", "cache coherence",
    "并发", "事务", "持久化", "生命周期", "历史状态", "选择状态", "竞态", "缓存一致性",
)
_RISK_HINTS = (
    "security", "authentication", "authorization", "permission", "credential", "billing",
    "payment", "migration", "database migration", "release", "production", "data loss",
    "backward compatibility", "compatibility-sensitive",
    "安全", "认证", "鉴权", "权限", "凭据", "计费", "支付", "迁移", "数据库迁移", "发布",
    "生产环境", "数据丢失", "向后兼容", "兼容性",
)
_CROSS_HINTS = (
    "cross-module", "cross module", "across modules", "multiple subsystems", "public api",
    "跨模块", "多个子系统", "公共接口",
)
_AMBIGUITY_HINTS = (
    "design", "figure out", "investigate root cause", "unclear cause", "unknown cause",
    "choose approach", "trade-off", "tradeoff",
    "设计方案", "定位根因", "原因不明", "选择方案", "权衡",
)


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(item in text for item in hints)


class DifficultyClassifier:
    """Deterministic V0.5 classifier with explainable, testable signals."""

    def classify(self, task: TaskSpec) -> DifficultyAssessment:
        text = " ".join(
            part for part in (task.title, task.prompt or "", " ".join(task.acceptance)) if part
        ).lower()

        if task.kind in {"test", "build"} and task.command is not None and not task.prompt:
            return DifficultyAssessment(
                level=ModelLevel.NONE,
                score=0,
                confidence="high",
                reason=f"deterministic {task.kind} command; no reasoning model required",
                factors=(f"kind:{task.kind}=NONE",),
                traits=("deterministic",),
            )

        score = _KIND_BASE.get(task.kind, 4)
        factors: list[str] = [f"kind:{task.kind} base={score}"]
        traits: set[str] = set()

        if task.kind in {"repo_search", "docs", "handoff", "simple_edit"}:
            traits.add("localized")
        if task.kind in {"normal_code", "complex_code"}:
            traits.add("coding")
        if task.kind in {"normal_debug", "hard_debug"}:
            traits.add("debugging")
        if task.kind in {"architecture", "planning"}:
            traits.add("architecture")
        if task.kind == "review" or task.role == TaskRole.REVIEWER:
            traits.add("review")

        if _contains_any(text, _LOW_HINTS):
            score -= 1
            factors.append("localized/mechanical wording -1")
            traits.add("localized")

        if _contains_any(text, _MEDIUM_HINTS):
            score += 1
            factors.append("ordinary implementation/debug signal +1")
            traits.add("implementation")

        if _contains_any(text, _ARCH_HINTS):
            score += 5
            factors.append("architecture/core-semantics signal +5")
            traits.add("architecture")

        if _contains_any(text, _STATE_HINTS):
            score += 4
            factors.append("state/lifecycle/concurrency signal +4")
            traits.add("stateful")

        if _contains_any(text, _RISK_HINTS):
            score += 6
            factors.append("high-impact domain/compatibility signal +6")
            traits.add("high-risk")

        if _contains_any(text, _CROSS_HINTS):
            score += 3
            factors.append("cross-module/public-interface signal +3")
            traits.add("cross-module")

        if _contains_any(text, _AMBIGUITY_HINTS):
            score += 2
            factors.append("design/root-cause ambiguity +2")
            traits.add("ambiguous")

        if task.require_diff:
            score += 1
            factors.append("code-change verification required +1")

        if task.review:
            score += 1
            factors.append("independent review requested +1")
            traits.add("review")

        if len(task.acceptance) >= 3:
            score += 1
            factors.append("broad acceptance surface +1")

        score = max(score, 1)

        if score <= 2:
            level = ModelLevel.LOW
        elif score <= 6:
            level = ModelLevel.MEDIUM
        else:
            level = ModelLevel.HIGH

        known_kind = task.kind in _KIND_BASE
        if score <= 1 or score >= 10:
            confidence = "high"
        elif not known_kind and len(factors) == 1:
            confidence = "low"
        else:
            confidence = "medium"

        reason_parts = [factors[0]]
        reason_parts.extend(factors[1:3])
        reason = "; ".join(reason_parts)

        return DifficultyAssessment(
            level=level,
            score=score,
            confidence=confidence,
            reason=reason,
            factors=tuple(factors),
            traits=tuple(sorted(traits)),
        )
