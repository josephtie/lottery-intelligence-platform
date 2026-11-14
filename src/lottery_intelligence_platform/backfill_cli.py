from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from lottery_intelligence_platform.backfill import BackfillWindow, collect_result_window
from lottery_intelligence_platform.catalog import ensure_lotobonheur_catalog
from lottery_intelligence_platform.collectors.lotobonheur import (
    LotobonheurResultCollector,
    ResultValidationRules,
)
from lottery_intelligence_platform.draw_registry import DrawRegistry
from lottery_intelligence_platform.raw_bucket import ensure_bucket
from lottery_intelligence_platform.storage import raw_object_store_from_environment, s3_client_from_environment


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lottery-backfill")
    window = parser.add_mutually_exclusive_group(required=True)
    window.add_argument("--full-history", action="store_true")
    window.add_argument("--months", type=int)
    parser.add_argument("--through", type=date.fromisoformat)
    parser.add_argument("--pause-seconds", type=float, default=0.5)
    return parser


class _ProgressCollector:
    def __init__(self, collector: LotobonheurResultCollector) -> None:
        self._collector = collector

    def collect(self, connection, raw_store, **kwargs):
        month_year = kwargs["month_year"]
        print(f"Collecting {month_year}", flush=True)
        try:
            batch = self._collector.collect(connection, raw_store, **kwargs)
        except Exception as exc:
            print(f"{month_year}: {type(exc).__name__}", flush=True)
            raise
        print(
            f"{month_year}: {len(batch.validation.observations)} valid, "
            f"{len(batch.validation.issues)} validation issues",
            flush=True,
        )
        return batch


def main() -> int:
    args = _parser().parse_args()
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)

    if args.full_history:
        window = BackfillWindow.available_history(through=args.through)
    else:
        if args.months < 1:
            raise SystemExit("--months must be positive")
        window = BackfillWindow.trailing_months(args.months, through=args.through)

    host = os.environ.get("LOTTERY_DATABASE_HOST", "localhost")
    port = int(os.environ.get("LOTTERY_DATABASE_PORT", "5432"))
    database = os.environ.get("LOTTERY_DATABASE_NAME", "lottery_platform")
    user = os.environ.get("LOTTERY_DATABASE_USER", "directus")
    bucket = os.environ.get("LOTTERY_S3_BUCKET", "").strip()
    if not bucket:
        raise SystemExit("LOTTERY_S3_BUCKET must be set in the environment")

    s3_client = s3_client_from_environment()
    ensure_bucket(s3_client, bucket)
    raw_store = raw_object_store_from_environment()

    with psycopg.connect(host=host, port=port, dbname=database, user=user) as connection:
        catalog = ensure_lotobonheur_catalog(connection, data_coverage_start=window.start_date)
        rules = ResultValidationRules.from_game_version(connection, catalog.game_version_id)
        connection.commit()
        collector = _ProgressCollector(LotobonheurResultCollector(rules=rules))
        registry = DrawRegistry(
            connection,
            game_id=catalog.game_id,
            game_version_id=catalog.game_version_id,
            source_id=catalog.source_id,
            auto_create_draw_types=True,
        )
        result = collect_result_window(
            collector,
            connection,
            raw_store,
            source_id=catalog.source_id,
            window=window,
            draw_registry=registry,
            pause_seconds=args.pause_seconds,
        )

    registrations = [registration for _, batch in result.registrations for registration in batch]
    summary = {
        "window": {"start": window.start_date.isoformat(), "end": window.end_date.isoformat()},
        "month_buckets": len(window.month_years()),
        "months_collected": len(result.batches),
        "valid_draw_observations": len(result.observations),
        "draw_types": len(result.coverage),
        "overlapping_rows": result.overlapping_observation_count,
        "identity_conflicts": len(result.conflicting_observations),
        "registry_conflicts": sum(registration.status == "CONFLICT" for registration in registrations),
        "failed_months": [asdict(failure) for failure in result.failures],
        "historical_rule_effectivity": "UNVERIFIED; exploratory data only",
        "complete": result.is_complete,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.is_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
