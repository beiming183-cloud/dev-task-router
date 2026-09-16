from __future__ import annotations

from .models import ModelLevel


_LEVELS = [ModelLevel.LOW, ModelLevel.MEDIUM, ModelLevel.HIGH]


def promote(level: ModelLevel, steps: int = 1) -> ModelLevel:
    if level == ModelLevel.NONE:
        return level
    index = _LEVELS.index(level)
    return _LEVELS[min(index + max(steps, 0), len(_LEVELS) - 1)]


def level_for_attempt(base: ModelLevel, attempt: int, escalate_after: int) -> ModelLevel:
    """Keep the base level through escalate_after, then promote one level per attempt."""
    if attempt <= escalate_after:
        return base
    return promote(base, attempt - escalate_after)
