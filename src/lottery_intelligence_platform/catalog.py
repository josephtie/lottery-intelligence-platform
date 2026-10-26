from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID, uuid4
from typing import Any

from psycopg.types.json import Jsonb


@dataclass(frozen=True, slots=True)
class LotoBonheurCatalog:
    source_id: UUID
    game_id: UUID
    game_version_id: UUID
    version: str


class CatalogConflict(RuntimeError):
    pass


# The official Loto Bonheur results archive begins on 2020-11-01. The game
# version is a property of that archive, NOT of the current collection window.
# Passing ``window.start_date`` here created a new "archive-provisional-<date>"
# version on every run and duplicated the recent draws.
ARCHIVE_START = date(2020, 11, 1)


def ensure_lotobonheur_catalog(
    connection: Any,
    *,
    data_coverage_start: date | None = None,
) -> LotoBonheurCatalog:
    if data_coverage_start is not None and data_coverage_start < ARCHIVE_START:
        raise ValueError("data_coverage_start predates the official results archive")

    coverage_start = ARCHIVE_START
    version = f"archive-provisional-{coverage_start.isoformat()}"
    rules = {
        "number_min": 1,
        "number_max": 90,
        "numbers_per_draw": 5,
        "duplicates_allowed": False,
        "official_rules_url": "https://www.lonaci.ci/loto_bonheur/",
        "historical_effectivity": "UNVERIFIED",
        "model_eligibility": "EXPLORATORY_ONLY",
    }

    with connection.transaction():
        source_id = _ensure_source(connection)
        game_id = _ensure_game(connection)
        game_version_id = _ensure_game_version(
            connection,
            game_id=game_id,
            version=version,
            effective_from=coverage_start,
            rules=rules,
        )
    return LotoBonheurCatalog(source_id, game_id, game_version_id, version)


def _ensure_source(connection: Any) -> UUID:
    source_id = uuid4()
    inserted = connection.execute(
        """INSERT INTO ingestion.sources
           (source_id, code, display_name, base_uri, source_kind)
           VALUES (%s, 'lotobonheur_official', 'Loto Bonheur official site', 'https://lotobonheur.ci/', 'OFFICIAL')
           ON CONFLICT (code) DO NOTHING
           RETURNING source_id""",
        (source_id,),
    ).fetchone()
    if inserted:
        return inserted[0]
    existing = connection.execute(
        """SELECT source_id, base_uri, source_kind FROM ingestion.sources
           WHERE code = 'lotobonheur_official'"""
    ).fetchone()
    if existing is None or existing[1] != "https://lotobonheur.ci/" or existing[2] != "OFFICIAL":
        raise CatalogConflict("existing Loto Bonheur source definition differs from this bootstrap")
    return existing[0]


def _ensure_game(connection: Any) -> UUID:
    game_id = uuid4()
    inserted = connection.execute(
        """INSERT INTO catalog.games
           (game_id, code, display_name, country_code, operator_name, timezone_name)
           VALUES (%s, 'loto_bonheur_ci', 'Loto Bonheur', 'CI', 'LONACI', 'Africa/Abidjan')
           ON CONFLICT (code) DO NOTHING
           RETURNING game_id""",
        (game_id,),
    ).fetchone()
    if inserted:
        return inserted[0]
    existing = connection.execute(
        """SELECT game_id, display_name, country_code, operator_name, timezone_name
           FROM catalog.games WHERE code = 'loto_bonheur_ci'"""
    ).fetchone()
    if existing is None or existing[1:] != ("Loto Bonheur", "CI", "LONACI", "Africa/Abidjan"):
        raise CatalogConflict("existing Loto Bonheur game definition differs from this bootstrap")
    return existing[0]


def _ensure_game_version(
    connection: Any,
    *,
    game_id: UUID,
    version: str,
    effective_from: date,
    rules: dict[str, object],
) -> UUID:
    game_version_id = uuid4()
    inserted = connection.execute(
        """INSERT INTO catalog.game_versions
           (game_version_id, game_id, version, effective_from, rules)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (game_id, version) DO NOTHING
           RETURNING game_version_id""",
        (game_version_id, game_id, version, effective_from, Jsonb(rules)),
    ).fetchone()
    if inserted:
        return inserted[0]
    existing = connection.execute(
        """SELECT game_version_id, effective_from, rules
           FROM catalog.game_versions WHERE game_id = %s AND version = %s""",
        (game_id, version),
    ).fetchone()
    if existing is None or existing[1] != effective_from or existing[2] != rules:
        raise CatalogConflict("existing provisional game version differs from this bootstrap")
    return existing[0]
