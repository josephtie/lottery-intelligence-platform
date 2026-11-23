from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DatasetSnapshotManifest:
    draw_version_ids: tuple[str, ...]
    cutoff_at: datetime
    schema_version: str
    code_version: str
    game_version_ids: tuple[str, ...] = ()
    historical_effectivity_statuses: tuple[str, ...] = ()
    model_eligibility_statuses: tuple[str, ...] = ()
    modeling_eligibility: str = "EXPLORATORY_ONLY"

    def __post_init__(self) -> None:
        if self.cutoff_at.tzinfo is None or self.cutoff_at.utcoffset() is None:
            raise ValueError("cutoff_at must be timezone-aware")
        if not self.schema_version.strip() or not self.code_version.strip():
            raise ValueError("schema_version and code_version cannot be empty")
        if not self.modeling_eligibility.strip():
            raise ValueError("modeling_eligibility cannot be empty")

        normalized_ids = tuple(sorted(str(UUID(value)) for value in self.draw_version_ids))
        normalized_game_versions = tuple(sorted(str(UUID(value)) for value in self.game_version_ids))
        if len(normalized_ids) != len(set(normalized_ids)):
            raise ValueError("draw_version_ids must be unique")
        if len(normalized_game_versions) != len(set(normalized_game_versions)):
            raise ValueError("game_version_ids must be unique")
        object.__setattr__(self, "draw_version_ids", normalized_ids)
        object.__setattr__(self, "game_version_ids", normalized_game_versions)
        object.__setattr__(self, "historical_effectivity_statuses", tuple(sorted(set(self.historical_effectivity_statuses))))
        object.__setattr__(self, "model_eligibility_statuses", tuple(sorted(set(self.model_eligibility_statuses))))
        object.__setattr__(self, "cutoff_at", self.cutoff_at.astimezone(timezone.utc))

    def to_dict(self) -> dict[str, object]:
        return {
            "format_version": 2,
            "draw_version_ids": list(self.draw_version_ids),
            "game_version_ids": list(self.game_version_ids),
            "cutoff_at": self.cutoff_at.isoformat(timespec="microseconds").replace("+00:00", "Z"),
            "schema_version": self.schema_version,
            "code_version": self.code_version,
            "historical_effectivity_statuses": list(self.historical_effectivity_statuses),
            "model_eligibility_statuses": list(self.model_eligibility_statuses),
            "modeling_eligibility": self.modeling_eligibility,
        }

    @property
    def sha256(self) -> str:
        canonical = json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


def compare_dataset_versions(
    left: DatasetSnapshotManifest, right: DatasetSnapshotManifest
) -> dict[str, object]:
    left_ids = set(left.draw_version_ids)
    right_ids = set(right.draw_version_ids)
    return {
        "same_manifest": left.sha256 == right.sha256,
        "added_draw_version_ids": sorted(right_ids - left_ids),
        "removed_draw_version_ids": sorted(left_ids - right_ids),
    }
