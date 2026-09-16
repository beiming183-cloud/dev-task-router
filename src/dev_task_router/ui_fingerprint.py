from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .config import autodev_dir


UI_FINGERPRINT_FILE = "ui-fingerprint.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _matches(name: str, labels: Iterable[str]) -> bool:
    value = _norm(name)
    return bool(value) and any(
        _norm(label) == value or (_norm(label) and _norm(label) in value)
        for label in labels
    )


@dataclass(frozen=True, slots=True)
class UIFingerprint:
    schema_version: int
    platform: str
    sources: tuple[str, ...]
    control_count: int
    stable_control_count: int
    tracked_hits: dict[str, int]
    digest: str
    captured_at: str

    @classmethod
    def from_rows(
        cls,
        rows_by_source: dict[str, list[dict[str, str]]],
        *,
        tracked_labels: dict[str, tuple[str, ...]] | None = None,
        platform: str | None = None,
    ) -> "UIFingerprint":
        tracked_labels = tracked_labels or {}
        hits = {key: 0 for key in sorted(tracked_labels)}
        stable_entries: list[str] = []
        total = 0

        for source in sorted(rows_by_source):
            rows = rows_by_source[source]
            total += len(rows)
            for row in rows:
                name = str(row.get("name", ""))
                control_type = _norm(row.get("control_type", ""))
                automation_id = str(row.get("automation_id", "")).strip()
                for key in sorted(tracked_labels):
                    if not _matches(name, tracked_labels[key]):
                        continue
                    hits[key] += 1
                    # Only controls that match configured selectors participate in the
                    # structural digest. Dynamic message/title automation ids are ignored.
                    # The configured label text itself is never persisted or hashed.
                    stable_entries.append(
                        f"{source}|tracked|{key}|{control_type}|{automation_id}"
                    )

        canonical = {
            "platform": platform or sys.platform,
            "sources": sorted(rows_by_source),
            "stable_entries": sorted(set(stable_entries)),
            "tracked_hits": hits,
        }
        payload = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return cls(
            schema_version=1,
            platform=platform or sys.platform,
            sources=tuple(sorted(rows_by_source)),
            control_count=total,
            stable_control_count=len(set(stable_entries)),
            tracked_hits=hits,
            digest=digest,
            captured_at=_now_iso(),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "UIFingerprint":
        if int(data.get("schema_version", 0)) != 1:
            raise ValueError("unsupported UI fingerprint schema")
        tracked = data.get("tracked_hits", {})
        if not isinstance(tracked, dict):
            raise ValueError("UI fingerprint tracked_hits must be a mapping")
        return cls(
            schema_version=1,
            platform=str(data.get("platform", "")),
            sources=tuple(str(item) for item in data.get("sources", [])),
            control_count=int(data.get("control_count", 0)),
            stable_control_count=int(data.get("stable_control_count", 0)),
            tracked_hits={str(key): int(value) for key, value in tracked.items()},
            digest=str(data.get("digest", "")),
            captured_at=str(data.get("captured_at", "")),
        )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "platform": self.platform,
            "sources": list(self.sources),
            "control_count": self.control_count,
            "stable_control_count": self.stable_control_count,
            "tracked_hits": dict(self.tracked_hits),
            "digest": self.digest,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True, slots=True)
class UIFingerprintComparison:
    status: str
    baseline_digest: str | None
    current_digest: str
    reasons: tuple[str, ...]

    @property
    def drifted(self) -> bool:
        return self.status == "DRIFT"

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "baseline_digest": self.baseline_digest,
            "current_digest": self.current_digest,
            "drifted": self.drifted,
            "reasons": list(self.reasons),
        }


class UIFingerprintStore:
    def __init__(self, root: Path):
        self.path = autodev_dir(root) / UI_FINGERPRINT_FILE

    def load(self) -> UIFingerprint | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("ui-fingerprint.json must contain an object")
        return UIFingerprint.from_dict(data)

    def save(self, fingerprint: UIFingerprint) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(fingerprint.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return self.path

    def compare(self, current: UIFingerprint) -> UIFingerprintComparison:
        baseline = self.load()
        if baseline is None:
            return UIFingerprintComparison(
                status="UNCALIBRATED",
                baseline_digest=None,
                current_digest=current.digest,
                reasons=("no recorded UI fingerprint baseline",),
            )

        reasons: list[str] = []
        if baseline.platform != current.platform:
            reasons.append(
                f"platform changed: {baseline.platform or 'unknown'} -> {current.platform or 'unknown'}"
            )
        if baseline.sources != current.sources:
            reasons.append("probe source set changed")
        if baseline.tracked_hits != current.tracked_hits:
            keys = sorted(set(baseline.tracked_hits) | set(current.tracked_hits))
            for key in keys:
                before = baseline.tracked_hits.get(key, 0)
                after = current.tracked_hits.get(key, 0)
                if before != after:
                    reasons.append(f"tracked selector {key!r} hits changed: {before} -> {after}")
        if baseline.digest != current.digest:
            reasons.append("calibrated selector structure digest changed")

        return UIFingerprintComparison(
            status="DRIFT" if reasons else "MATCH",
            baseline_digest=baseline.digest,
            current_digest=current.digest,
            reasons=tuple(reasons),
        )
