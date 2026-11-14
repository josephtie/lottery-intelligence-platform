from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

from lottery_intelligence_platform.artifacts import S3ArtifactStore, export_dataset_artifact
from lottery_intelligence_platform.dataset_repository import create_dataset_snapshot
from lottery_intelligence_platform.storage import s3_client_from_environment


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lottery-dataset-snapshot")
    parser.add_argument("--dataset-code", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--cutoff-at", required=True, type=datetime.fromisoformat)
    return parser


def main() -> int:
    args = _parser().parse_args()
    load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)

    host = os.environ.get("LOTTERY_DATABASE_HOST", "localhost")
    port = int(os.environ.get("LOTTERY_DATABASE_PORT", "5432"))
    database = os.environ.get("LOTTERY_DATABASE_NAME", "lottery_platform")
    user = os.environ.get("LOTTERY_DATABASE_USER", "directus")
    bucket = os.environ.get("LOTTERY_S3_BUCKET", "").strip()
    if not bucket:
        raise SystemExit("LOTTERY_S3_BUCKET must be set in the environment")

    with psycopg.connect(host=host, port=port, dbname=database, user=user) as connection:
        snapshot = create_dataset_snapshot(
            connection,
            dataset_code=args.dataset_code,
            display_name=args.display_name,
            cutoff_at=args.cutoff_at,
        )
        artifacts = export_dataset_artifact(
            connection,
            S3ArtifactStore(s3_client_from_environment(), bucket),
            dataset_version_id=str(snapshot.dataset_version_id),
            dataset_code=args.dataset_code,
        )

    manifest_ref, parquet_ref = artifacts
    print(json.dumps({
        "dataset_version_id": str(snapshot.dataset_version_id),
        "version_number": snapshot.version_number,
        "created": snapshot.created,
        "member_count": len(snapshot.manifest.draw_version_ids),
        "modeling_eligibility": snapshot.manifest.modeling_eligibility,
        "manifest_sha256": snapshot.manifest.sha256,
        "manifest_artifact_sha256": manifest_ref.sha256,
        "manifest_object_key": manifest_ref.object_key,
        "parquet_artifact_sha256": parquet_ref.sha256,
        "parquet_object_key": parquet_ref.object_key,
        "parquet_rows": parquet_ref.row_count,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
