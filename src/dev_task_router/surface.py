from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import ModelLevel


@dataclass(frozen=True, slots=True)
class SurfaceModel:
    family: str
    effort: str | None = None
    label: str | None = None


@dataclass(frozen=True, slots=True)
class SurfaceDecision:
    surface: str
    level: ModelLevel
    resolved: bool
    model: SurfaceModel | None
    candidate_families: tuple[str, ...]
    candidate_efforts: tuple[str, ...]
    reason: str


@dataclass(slots=True)
class SurfaceProfile:
    name: str
    strategy: str
    routes: dict[ModelLevel, SurfaceModel]
    families: tuple[str, ...] = ()
    efforts: tuple[str, ...] = ()


@dataclass(slots=True)
class SurfaceCatalog:
    default_surface: str
    surfaces: dict[str, SurfaceProfile]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SurfaceCatalog":
        default_surface = str(data.get("default_surface", "chat")).strip().lower()
        raw_surfaces = data.get("surfaces")
        if not isinstance(raw_surfaces, dict) or not raw_surfaces:
            raise ValueError("surfaces.surfaces must be a non-empty mapping")

        surfaces: dict[str, SurfaceProfile] = {}
        for raw_name, raw in raw_surfaces.items():
            name = str(raw_name).strip().lower()
            if not name or not isinstance(raw, dict):
                raise ValueError("every surface must be a named mapping")

            strategy = str(raw.get("strategy", "fixed")).strip().lower()
            if strategy not in {"fixed", "pool"}:
                raise ValueError(f"surface {name}: strategy must be fixed or pool")

            families = tuple(str(x).strip() for x in raw.get("families", []) if str(x).strip())
            efforts = tuple(str(x).strip() for x in raw.get("efforts", []) if str(x).strip())
            raw_routes = raw.get("routes", {})
            if not isinstance(raw_routes, dict):
                raise ValueError(f"surface {name}: routes must be a mapping")

            routes: dict[ModelLevel, SurfaceModel] = {}
            for raw_level, raw_model in raw_routes.items():
                try:
                    level = ModelLevel(str(raw_level).upper())
                except ValueError as exc:
                    raise ValueError(f"surface {name}: invalid level {raw_level}") from exc
                if level == ModelLevel.NONE:
                    continue
                if not isinstance(raw_model, dict):
                    raise ValueError(f"surface {name}/{level.value}: route must be a mapping")
                family = str(raw_model.get("family", "")).strip()
                effort_value = raw_model.get("effort")
                effort = str(effort_value).strip() if effort_value is not None else None
                label_value = raw_model.get("label")
                label = str(label_value).strip() if label_value is not None else None
                if not family:
                    raise ValueError(f"surface {name}/{level.value}: family is required")
                routes[level] = SurfaceModel(family=family, effort=effort or None, label=label or None)

            if strategy == "fixed":
                missing = [
                    level.value
                    for level in (ModelLevel.LOW, ModelLevel.MEDIUM, ModelLevel.HIGH)
                    if level not in routes
                ]
                if missing:
                    raise ValueError(f"surface {name}: fixed routes missing {', '.join(missing)}")
            elif not families or not efforts:
                raise ValueError(f"surface {name}: pool strategy requires families and efforts")

            surfaces[name] = SurfaceProfile(
                name=name,
                strategy=strategy,
                routes=routes,
                families=families,
                efforts=efforts,
            )

        if default_surface not in surfaces:
            raise ValueError(f"default surface not found: {default_surface}")
        return cls(default_surface=default_surface, surfaces=surfaces)

    def route(self, level: ModelLevel, surface: str | None = None) -> SurfaceDecision:
        name = (surface or self.default_surface).strip().lower()
        if name not in self.surfaces:
            raise ValueError(f"unknown surface: {name}")
        profile = self.surfaces[name]

        if level == ModelLevel.NONE:
            return SurfaceDecision(
                surface=name,
                level=level,
                resolved=True,
                model=None,
                candidate_families=(),
                candidate_efforts=(),
                reason="NONE is deterministic and does not require a model",
            )

        configured = profile.routes.get(level)
        if configured is not None:
            return SurfaceDecision(
                surface=name,
                level=level,
                resolved=True,
                model=configured,
                candidate_families=(),
                candidate_efforts=(),
                reason=f"configured {name}/{level.value} route",
            )

        return SurfaceDecision(
            surface=name,
            level=level,
            resolved=False,
            model=None,
            candidate_families=profile.families,
            candidate_efforts=profile.efforts,
            reason=(
                f"{name} exposes a model pool but no {level.value} route is configured; "
                "do not invent a family ranking"
            ),
        )
