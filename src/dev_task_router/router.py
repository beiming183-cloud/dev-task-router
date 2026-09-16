from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ModelLevel, TaskSpec


@dataclass(frozen=True, slots=True)
class ModelProfile:
    level: ModelLevel
    provider: str
    model: str
    executor: str
    command: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class RoutingDecision:
    level: ModelLevel
    profile: ModelProfile
    reason: str


@dataclass(slots=True)
class ModelCatalog:
    profiles: dict[ModelLevel, ModelProfile]
    rules: dict[str, ModelLevel]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelCatalog":
        raw_profiles = data.get("profiles")
        if not isinstance(raw_profiles, dict):
            raise ValueError("models.profiles must be a mapping")

        profiles: dict[ModelLevel, ModelProfile] = {}
        for raw_level, raw_profile in raw_profiles.items():
            try:
                level = ModelLevel(str(raw_level).upper())
            except ValueError as exc:
                raise ValueError(f"unknown model level: {raw_level}") from exc
            if not isinstance(raw_profile, dict):
                raise ValueError(f"profile {level.value} must be a mapping")
            provider = str(raw_profile.get("provider", "")).strip()
            model = str(raw_profile.get("model", "")).strip()
            executor = str(raw_profile.get("executor", "")).strip()
            raw_command = raw_profile.get("command")
            command: tuple[str, ...] | None = None
            if raw_command is not None:
                if (
                    not isinstance(raw_command, list)
                    or not raw_command
                    or not all(isinstance(x, str) for x in raw_command)
                ):
                    raise ValueError(f"profile {level.value}: command must be a non-empty string list")
                command = tuple(raw_command)
            if not provider or not model or not executor:
                raise ValueError(f"profile {level.value} requires provider, model and executor")
            profiles[level] = ModelProfile(level, provider, model, executor, command)

        missing = [level.value for level in ModelLevel if level not in profiles]
        if missing:
            raise ValueError(f"models.profiles missing levels: {', '.join(missing)}")

        raw_rules = data.get("rules", {})
        if not isinstance(raw_rules, dict):
            raise ValueError("models.rules must be a mapping")
        rules: dict[str, ModelLevel] = {}
        for kind, raw_level in raw_rules.items():
            key = str(kind).strip().lower()
            if not key:
                raise ValueError("routing rule kind cannot be empty")
            try:
                rules[key] = ModelLevel(str(raw_level).upper())
            except ValueError as exc:
                raise ValueError(f"rule {kind}: invalid model level {raw_level}") from exc

        return cls(profiles=profiles, rules=rules)


class RuleRouter:
    def __init__(self, catalog: ModelCatalog):
        self.catalog = catalog

    def decision_for_level(self, level: ModelLevel, reason: str) -> RoutingDecision:
        return RoutingDecision(level=level, profile=self.catalog.profiles[level], reason=reason)

    def route(
        self,
        task: TaskSpec,
        *,
        override_level: ModelLevel | None = None,
        override_reason: str | None = None,
    ) -> RoutingDecision:
        if override_level is not None:
            return self.decision_for_level(
                override_level,
                override_reason or f"override:{override_level.value}",
            )
        if task.level is not None:
            level = task.level
            reason = "explicit task level"
        else:
            level = self.catalog.rules.get(task.kind, ModelLevel.MEDIUM)
            reason = f"rule:{task.kind}" if task.kind in self.catalog.rules else "default:MEDIUM"
        return self.decision_for_level(level, reason)
