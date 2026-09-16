from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import autodev_dir
from .mode_switch import SwitchResult
from .models import ModelLevel
from .state import now_iso


PROFILE_CALIBRATION_FILE = "profile-calibration.json"


@dataclass(frozen=True, slots=True)
class ProfileCalibrationRecord:
    level: ModelLevel
    family: str
    effort: str | None
    ui_fingerprint: str
    switch_verified: bool
    end_to_end_verified: bool
    evidence_dispatch_id: str | None
    verified_at: str

    @classmethod
    def from_dict(cls, data: dict) -> "ProfileCalibrationRecord":
        if not isinstance(data, dict):
            raise ValueError("profile calibration record must be an object")
        return cls(
            level=ModelLevel(str(data.get("level", "")).upper()),
            family=str(data.get("family", "")).strip(),
            effort=(str(data["effort"]).strip() if data.get("effort") is not None else None),
            ui_fingerprint=str(data.get("ui_fingerprint", "")).strip(),
            switch_verified=bool(data.get("switch_verified", False)),
            end_to_end_verified=bool(data.get("end_to_end_verified", False)),
            evidence_dispatch_id=(
                str(data["evidence_dispatch_id"]).strip()
                if data.get("evidence_dispatch_id")
                else None
            ),
            verified_at=str(data.get("verified_at", "")).strip(),
        )

    def to_dict(self) -> dict:
        return {
            "level": self.level.value,
            "family": self.family,
            "effort": self.effort,
            "ui_fingerprint": self.ui_fingerprint,
            "switch_verified": self.switch_verified,
            "end_to_end_verified": self.end_to_end_verified,
            "evidence_dispatch_id": self.evidence_dispatch_id,
            "verified_at": self.verified_at,
        }


@dataclass(frozen=True, slots=True)
class CalibrationCoverage:
    ui_fingerprint: str | None
    valid_levels: tuple[str, ...]
    stale_levels: tuple[str, ...]
    missing_levels: tuple[str, ...]
    e2e_levels: tuple[str, ...]

    @property
    def switch_complete(self) -> bool:
        return not self.missing_levels and not self.stale_levels

    @property
    def end_to_end_complete(self) -> bool:
        return self.switch_complete and set(self.e2e_levels) == {
            ModelLevel.LOW.value,
            ModelLevel.MEDIUM.value,
            ModelLevel.HIGH.value,
        }

    def to_dict(self) -> dict:
        return {
            "ui_fingerprint": self.ui_fingerprint,
            "valid_levels": list(self.valid_levels),
            "stale_levels": list(self.stale_levels),
            "missing_levels": list(self.missing_levels),
            "e2e_levels": list(self.e2e_levels),
            "switch_complete": self.switch_complete,
            "end_to_end_complete": self.end_to_end_complete,
        }


class ProfileCalibrationRegistry:
    """Store live profile verification bound to one privacy-safe UI fingerprint.

    The registry cannot create verification from a requested profile alone. A switch
    record is accepted only from a `SwitchResult` whose backend actually reported
    `verified=True`. End-to-end verification is a separate later boundary.
    """

    REQUIRED_LEVELS = (ModelLevel.LOW, ModelLevel.MEDIUM, ModelLevel.HIGH)

    def __init__(self, root: Path):
        self.path = autodev_dir(root) / PROFILE_CALIBRATION_FILE

    def _load_data(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "profiles": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or int(data.get("schema_version", 0)) != 1:
            raise ValueError("unsupported profile calibration schema")
        profiles = data.get("profiles", {})
        if not isinstance(profiles, dict):
            raise ValueError("profile calibration profiles must be a mapping")
        return data

    def _save_data(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def records(self) -> dict[ModelLevel, ProfileCalibrationRecord]:
        data = self._load_data()
        result: dict[ModelLevel, ProfileCalibrationRecord] = {}
        for raw_level, raw_record in data["profiles"].items():
            level = ModelLevel(str(raw_level).upper())
            if level == ModelLevel.NONE:
                continue
            record = ProfileCalibrationRecord.from_dict(raw_record)
            if record.level != level:
                raise ValueError(f"profile calibration key/record mismatch for {level.value}")
            result[level] = record
        return result

    def record_verified_switch(
        self,
        result: SwitchResult,
        *,
        ui_fingerprint: str,
    ) -> ProfileCalibrationRecord:
        if not result.verified:
            raise ValueError("cannot record an unverified profile switch as calibration")
        if result.requested.level == ModelLevel.NONE:
            raise ValueError("NONE has no ChatGPT profile calibration")
        fingerprint = ui_fingerprint.strip()
        if not fingerprint:
            raise ValueError("UI fingerprint is required for profile calibration")
        if result.actual_family != result.requested.family:
            raise ValueError("actual family does not match requested family")
        if result.actual_effort != result.requested.effort:
            raise ValueError("actual effort does not match requested effort")

        record = ProfileCalibrationRecord(
            level=result.requested.level,
            family=result.actual_family or result.requested.family,
            effort=result.actual_effort,
            ui_fingerprint=fingerprint,
            switch_verified=True,
            end_to_end_verified=False,
            evidence_dispatch_id=None,
            verified_at=now_iso(),
        )
        data = self._load_data()
        data["profiles"][record.level.value] = record.to_dict()
        self._save_data(data)
        return record

    def mark_end_to_end_verified(
        self,
        level: ModelLevel,
        *,
        ui_fingerprint: str,
        dispatch_id: str,
    ) -> ProfileCalibrationRecord:
        if level == ModelLevel.NONE:
            raise ValueError("NONE has no end-to-end profile calibration")
        dispatch = dispatch_id.strip()
        if not dispatch:
            raise ValueError("dispatch_id is required for end-to-end verification")
        records = self.records()
        record = records.get(level)
        if record is None or not record.switch_verified:
            raise ValueError(f"{level.value} switch must be verified before end-to-end calibration")
        if record.ui_fingerprint != ui_fingerprint:
            raise ValueError("profile calibration is stale for the current UI fingerprint")

        updated = ProfileCalibrationRecord(
            level=record.level,
            family=record.family,
            effort=record.effort,
            ui_fingerprint=record.ui_fingerprint,
            switch_verified=True,
            end_to_end_verified=True,
            evidence_dispatch_id=dispatch,
            verified_at=now_iso(),
        )
        data = self._load_data()
        data["profiles"][level.value] = updated.to_dict()
        self._save_data(data)
        return updated

    def coverage(self, ui_fingerprint: str | None) -> CalibrationCoverage:
        records = self.records()
        valid: list[str] = []
        stale: list[str] = []
        missing: list[str] = []
        e2e: list[str] = []
        for level in self.REQUIRED_LEVELS:
            record = records.get(level)
            if record is None or not record.switch_verified:
                missing.append(level.value)
                continue
            if not ui_fingerprint or record.ui_fingerprint != ui_fingerprint:
                stale.append(level.value)
                continue
            valid.append(level.value)
            if record.end_to_end_verified and record.evidence_dispatch_id:
                e2e.append(level.value)
        return CalibrationCoverage(
            ui_fingerprint=ui_fingerprint,
            valid_levels=tuple(valid),
            stale_levels=tuple(stale),
            missing_levels=tuple(missing),
            e2e_levels=tuple(e2e),
        )
