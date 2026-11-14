from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping
from uuid import uuid4

import duckdb
from botocore.exceptions import ClientError
from psycopg.types.json import Jsonb


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    sha256: str
    byte_size: int
    row_count: int
    object_key: str


class ArtifactConflict(RuntimeError):
    pass


class ArtifactStore:
    def put_if_absent(self, key: str, payload: bytes, media_type: str) -> bool:
        raise NotImplementedError


class LocalArtifactStore(ArtifactStore):
    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._directory.mkdir(parents=True, exist_ok=True)

    def put_if_absent(self, key: str, payload: bytes, media_type: str) -> bool:
        path = self._directory / key.replace("/", "_")
        if path.exists():
            if path.read_bytes() != payload:
                raise ArtifactConflict(f"artifact exists with different content: {key}")
            return False
        path.write_bytes(payload)
        return True


class S3ArtifactStore(ArtifactStore):
    def __init__(self, client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def put_if_absent(self, key: str, payload: bytes, media_type: str) -> bool:
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=payload,
                ContentType=media_type,
                IfNoneMatch="*",
            )
            return True
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if code in {"PreconditionFailed", "ConditionalRequestConflict"} or status == 412:
                existing = self._client.get_object(Bucket=self._bucket, Key=key)["Body"].read()
                if existing == payload:
                    return False
                raise ArtifactConflict(f"S3 artifact exists with different content: {key}") from exc
            raise


def manifest_key(dataset_version_id: str, sha256: str) -> str:
    return f"datasets/{dataset_version_id}/manifest-{sha256}.json"


def parquet_key(dataset_version_id: str, sha256: str) -> str:
    return f"datasets/{dataset_version_id}/draw_numbers-{sha256}.parquet"


def write_parquet_rows(rows: Iterable[Mapping[str, object]]) -> bytes:
    rows = list(rows)
    with tempfile.TemporaryDirectory() as temp_dir:
        input_path = Path(temp_dir) / "rows.jsonl"
        parquet_path = Path(temp_dir) / "data.parquet"
        with input_path.open("w", encoding="utf-8") as input_file:
            for row in rows:
                input_file.write(json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":")))
                input_file.write("\n")
        with duckdb.connect(":memory:") as connection:
            connection.execute(
                """CREATE TABLE data AS
                   SELECT * FROM read_json(
                       ?,
                       columns={
                           draw_version_id: 'UUID',
                           draw_id: 'UUID',
                           scheduled_date: 'DATE',
                           draw_name: 'VARCHAR',
                           result_group: 'VARCHAR',
                           number_role: 'VARCHAR',
                           number_position: 'INTEGER',
                           number_value: 'INTEGER',
                           result_observed_at: 'TIMESTAMPTZ',
                           validated_at: 'TIMESTAMPTZ',
                           confirmed_at: 'TIMESTAMPTZ',
                           raw_object_sha256: 'VARCHAR',
                           dataset_version_id: 'VARCHAR',
                           manifest_sha256: 'VARCHAR'
                       },
                       format='newline_delimited'
                   )""",
                (str(input_path),),
            )
            connection.execute(
                """COPY (
                       SELECT * FROM data
                       ORDER BY draw_version_id,
                                CASE number_role WHEN 'WINNING' THEN 0 ELSE 1 END,
                                number_position
                   ) TO ? (FORMAT PARQUET)""",
                (str(parquet_path),),
            )
        return parquet_path.read_bytes()


def export_dataset_artifact(
    connection,
    store: ArtifactStore,
    *,
    dataset_version_id: str,
    dataset_code: str,
) -> tuple[ArtifactRef, ArtifactRef]:
    with connection.transaction():
        snapshot = connection.execute(
            """SELECT dv.version_number, dv.manifest, dv.manifest_sha256, dv.cutoff_at, d.code
               FROM datasets.dataset_versions dv
               JOIN datasets.datasets d ON d.dataset_id = dv.dataset_id
               WHERE dv.dataset_version_id = %s""",
            (dataset_version_id,),
        ).fetchone()
        if snapshot is None:
            raise ValueError("dataset_version_id not found")
        version_number, manifest, manifest_sha256, cutoff_at, stored_dataset_code = snapshot
        if stored_dataset_code != dataset_code:
            raise ValueError("dataset_code does not match the stored snapshot")

        rows = connection.execute(
            """SELECT m.ordinal, dv.draw_version_id, d.draw_id, d.scheduled_date,
                      dt.display_name, dv.result_metadata->>'result_group',
                      dn.number_role, dn.position, dn.number,
                      dv.result_observed_at, dv.validated_at, dv.confirmed_at, ro.sha256
               FROM datasets.dataset_members m
               JOIN core.draw_versions dv ON dv.draw_version_id = m.draw_version_id
               JOIN core.draws d ON d.draw_id = dv.draw_id
               JOIN catalog.draw_types dt ON dt.draw_type_id = d.draw_type_id
               JOIN core.draw_numbers dn ON dn.draw_version_id = dv.draw_version_id
               JOIN ingestion.raw_objects ro ON ro.raw_object_id = dv.raw_object_id
               WHERE m.dataset_version_id = %s
               ORDER BY m.ordinal,
                        CASE dn.number_role WHEN 'WINNING' THEN 0 ELSE 1 END,
                        dn.position""",
            (dataset_version_id,),
        ).fetchall()

    manifest_payload = json.dumps(
        {
            "dataset_version_id": dataset_version_id,
            "dataset_code": dataset_code,
            "version_number": version_number,
            "cutoff_at": cutoff_at.isoformat(),
            "manifest_sha256": manifest_sha256,
            "manifest": manifest,
        },
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    ).encode("utf-8")
    manifest_sha = hashlib.sha256(manifest_payload).hexdigest()
    manifest_key_path = manifest_key(dataset_version_id, manifest_sha)
    store.put_if_absent(manifest_key_path, manifest_payload, "application/json")
    manifest_ref = ArtifactRef(
        sha256=manifest_sha,
        byte_size=len(manifest_payload),
        row_count=len(manifest.get("draw_version_ids", [])),
        object_key=manifest_key_path,
    )

    parquet_rows = (
        {
            "draw_version_id": row[1],
            "draw_id": row[2],
            "scheduled_date": row[3],
            "draw_name": row[4],
            "result_group": row[5],
            "number_role": row[6],
            "number_position": row[7],
            "number_value": row[8],
            "result_observed_at": row[9],
            "validated_at": row[10],
            "confirmed_at": row[11],
            "raw_object_sha256": row[12],
            "dataset_version_id": dataset_version_id,
            "manifest_sha256": manifest_sha256,
        }
        for row in rows
    )
    parquet_payload = write_parquet_rows(parquet_rows)
    parquet_sha = hashlib.sha256(parquet_payload).hexdigest()
    parquet_key_path = parquet_key(dataset_version_id, parquet_sha)
    store.put_if_absent(parquet_key_path, parquet_payload, "application/vnd.apache.parquet")
    parquet_ref = ArtifactRef(
        sha256=parquet_sha,
        byte_size=len(parquet_payload),
        row_count=len(rows),
        object_key=parquet_key_path,
    )

    with connection.transaction():
        for artifact, artifact_type in (
            (manifest_ref, "MANIFEST_JSON"),
            (parquet_ref, "DRAW_NUMBERS_PARQUET"),
        ):
            connection.execute(
                """INSERT INTO datasets.dataset_artifacts
                   (dataset_artifact_id, dataset_version_id, artifact_type, storage_backend,
                    object_key, sha256, byte_size, row_count, media_type, metadata)
                   VALUES (%s, %s, %s, 'S3', %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (dataset_version_id, artifact_type, sha256) DO NOTHING""",
                (
                    uuid4(),
                    dataset_version_id,
                    artifact_type,
                    artifact.object_key,
                    artifact.sha256,
                    artifact.byte_size,
                    artifact.row_count,
                    "application/json" if artifact_type == "MANIFEST_JSON" else "application/vnd.apache.parquet",
                    Jsonb({"dataset_code": dataset_code}),
                ),
            )
    return manifest_ref, parquet_ref
