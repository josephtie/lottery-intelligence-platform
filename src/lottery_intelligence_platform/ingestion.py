from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.raw import RawObjectIntegrityError, RawObjectRef, RawObjectStore


@dataclass(frozen=True, slots=True)
class CollectionReceipt:
    collection_run_id: UUID
    collection_event_id: UUID
    ingestion_event_id: UUID
    raw_object_id: UUID
    raw_object: RawObjectRef


def ingest_payload(
    connection: Any,
    raw_store: RawObjectStore,
    *,
    source_id: UUID,
    collector_name: str,
    collector_version: str,
    payload: bytes,
    content_type: str = "application/octet-stream",
    response_status: int | None = None,
    external_identifiers: dict[str, Any] | None = None,
    observed_at: datetime | None = None,
    request_metadata: dict[str, Any] | None = None,
) -> CollectionReceipt:
    if not isinstance(source_id, UUID):
        raise TypeError("source_id must be a UUID")
    if not collector_name.strip() or not collector_version.strip():
        raise ValueError("collector_name and collector_version cannot be empty")
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if response_status is not None and (
        isinstance(response_status, bool)
        or not isinstance(response_status, int)
        or not 100 <= response_status <= 599
    ):
        raise ValueError("response_status must be an HTTP status code")

    identifiers = {} if external_identifiers is None else external_identifiers
    if not isinstance(identifiers, dict):
        raise TypeError("external_identifiers must be a dictionary")
    try:
        json.dumps(identifiers, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("external_identifiers must contain JSON-compatible values") from exc

    metadata = {} if request_metadata is None else request_metadata
    if not isinstance(metadata, dict):
        raise TypeError("request_metadata must be a dictionary")
    try:
        json.dumps(metadata, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("request_metadata must contain JSON-compatible values") from exc

    observed = observed_at or datetime.now(timezone.utc)
    if observed.tzinfo is None or observed.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    observed = observed.astimezone(timezone.utc)

    started_at = datetime.now(timezone.utc)
    collection_run_id = uuid4()
    with connection.transaction():
        connection.execute(
            """INSERT INTO ingestion.collection_runs
               (collection_run_id, source_id, collector_name, collector_version,
                started_at, status, request_metadata)
               VALUES (%s, %s, %s, %s, %s, 'RUNNING', %s)""",
            (collection_run_id, source_id, collector_name, collector_version, started_at, Jsonb(metadata)),
        )

    try:
        raw_object = raw_store.put(payload, content_type)
    except Exception as exc:
        try:
            _record_failure(
                connection,
                collection_run_id,
                "RAW_STORAGE_ERROR",
                exc,
                identifiers,
                response_status,
                observed,
            )
        except Exception as recording_error:
            exc.add_note(f"collection failure record also failed: {type(recording_error).__name__}")
        raise

    collection_event_id = uuid4()
    ingestion_event_id = uuid4()
    finished_at = datetime.now(timezone.utc)
    try:
        with connection.transaction():
            raw_object_id = _register_raw_object(connection, raw_object)
            details = {
                "sha256": raw_object.sha256,
                "object_key": raw_object.object_key,
                "byte_size": raw_object.byte_size,
                "media_type": content_type,
                "storage_backend": "S3",
            }
            connection.execute(
                """INSERT INTO ingestion.collection_events
                   (collection_event_id, collection_run_id, event_ordinal,
                    raw_object_id, event_type, external_identifiers,
                    response_status, observed_at, details)
                   VALUES (%s, %s, 1, %s, 'PAYLOAD_RECEIVED', %s, %s, %s, %s)""",
                (
                    collection_event_id,
                    collection_run_id,
                    raw_object_id,
                    Jsonb(identifiers),
                    response_status,
                    observed,
                    Jsonb(details),
                ),
            )
            connection.execute(
                """INSERT INTO ingestion.ingestion_events
                   (ingestion_event_id, collection_event_id, event_type,
                    subject_type, subject_id, details)
                   VALUES (%s, %s, 'RAW_OBJECT_REGISTERED', 'raw_object', %s, %s)""",
                (ingestion_event_id, collection_event_id, raw_object_id, Jsonb(details)),
            )
            connection.execute(
                """UPDATE ingestion.collection_runs
                   SET status = 'SUCCEEDED', finished_at = %s
                   WHERE collection_run_id = %s AND status = 'RUNNING'""",
                (finished_at, collection_run_id),
            )
    except Exception as exc:
        try:
            _record_failure(
                connection,
                collection_run_id,
                "REGISTRATION_ERROR",
                exc,
                identifiers,
                response_status,
                observed,
                raw_object,
            )
        except Exception as recording_error:
            exc.add_note(f"collection failure record also failed: {type(recording_error).__name__}")
        raise

    return CollectionReceipt(
        collection_run_id,
        collection_event_id,
        ingestion_event_id,
        raw_object_id,
        raw_object,
    )


def _register_raw_object(connection: Any, raw_object: RawObjectRef) -> UUID:
    inserted = connection.execute(
        """INSERT INTO ingestion.raw_objects
           (raw_object_id, sha256, object_key, byte_size, media_type, storage_backend)
           VALUES (%s, %s, %s, %s, %s, 'S3')
           ON CONFLICT (sha256) DO NOTHING
           RETURNING raw_object_id""",
        (
            uuid4(),
            raw_object.sha256,
            raw_object.object_key,
            raw_object.byte_size,
            raw_object.content_type,
        ),
    ).fetchone()
    if inserted:
        return inserted[0]

    existing = connection.execute(
        """SELECT raw_object_id, object_key, byte_size, storage_backend
           FROM ingestion.raw_objects WHERE sha256 = %s""",
        (raw_object.sha256,),
    ).fetchone()
    if existing is None or (
        existing[1] != raw_object.object_key
        or existing[2] != raw_object.byte_size
        or existing[3] != "S3"
    ):
        raise RawObjectIntegrityError("registered RAW metadata does not match its content address")
    return existing[0]


def _record_failure(
    connection: Any,
    collection_run_id: UUID,
    event_type: str,
    error: Exception,
    external_identifiers: dict[str, Any],
    response_status: int | None,
    observed_at: datetime,
    raw_object: RawObjectRef | None = None,
) -> None:
    details: dict[str, Any] = {"error_type": type(error).__name__}
    if raw_object is not None:
        details.update(
            sha256=raw_object.sha256,
            object_key=raw_object.object_key,
            byte_size=raw_object.byte_size,
        )
    with connection.transaction():
        updated = connection.execute(
            """UPDATE ingestion.collection_runs
               SET status = 'FAILED', finished_at = %s, error_summary = %s
               WHERE collection_run_id = %s AND status = 'RUNNING'
               RETURNING collection_run_id""",
            (datetime.now(timezone.utc), type(error).__name__, collection_run_id),
        ).fetchone()
        if updated is None:
            raise RuntimeError("collection run was not in RUNNING state")
        connection.execute(
            """INSERT INTO ingestion.collection_events
               (collection_event_id, collection_run_id, event_ordinal,
                event_type, external_identifiers, response_status, observed_at, details)
               VALUES (%s, %s, 1, %s, %s, %s, %s, %s)""",
            (
                uuid4(),
                collection_run_id,
                event_type,
                Jsonb(external_identifiers),
                response_status,
                observed_at,
                Jsonb(details),
            ),
        )


def record_collection_failure(
    connection: Any,
    *,
    source_id: UUID,
    collector_name: str,
    collector_version: str,
    error_type: str,
    request_metadata: dict[str, Any],
    response_status: int | None = None,
    external_identifiers: dict[str, Any] | None = None,
    observed_at: datetime | None = None,
) -> tuple[UUID, UUID]:
    if not isinstance(source_id, UUID):
        raise TypeError("source_id must be a UUID")
    if not collector_name.strip() or not collector_version.strip() or not error_type.strip():
        raise ValueError("collector and error names cannot be empty")
    if response_status is not None and (
        isinstance(response_status, bool)
        or not isinstance(response_status, int)
        or not 100 <= response_status <= 599
    ):
        raise ValueError("response_status must be an HTTP status code")

    metadata = dict(request_metadata)
    identifiers = {} if external_identifiers is None else external_identifiers
    try:
        json.dumps(metadata, ensure_ascii=False, allow_nan=False)
        json.dumps(identifiers, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("collection metadata must contain JSON-compatible values") from exc
    if not isinstance(identifiers, dict):
        raise TypeError("external_identifiers must be a dictionary")

    occurred_at = observed_at or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    occurred_at = occurred_at.astimezone(timezone.utc)
    collection_run_id, collection_event_id = uuid4(), uuid4()
    with connection.transaction():
        connection.execute(
            """INSERT INTO ingestion.collection_runs
               (collection_run_id, source_id, collector_name, collector_version,
                started_at, finished_at, status, request_metadata, error_summary)
               VALUES (%s, %s, %s, %s, %s, %s, 'FAILED', %s, %s)""",
            (
                collection_run_id,
                source_id,
                collector_name,
                collector_version,
                occurred_at,
                occurred_at,
                Jsonb(metadata),
                error_type,
            ),
        )
        connection.execute(
            """INSERT INTO ingestion.collection_events
               (collection_event_id, collection_run_id, event_ordinal, event_type,
                external_identifiers, response_status, observed_at, details)
               VALUES (%s, %s, 1, 'HTTP_ERROR', %s, %s, %s, %s)""",
            (
                collection_event_id,
                collection_run_id,
                Jsonb(identifiers),
                response_status,
                occurred_at,
                Jsonb({"error_type": error_type}),
            ),
        )
    return collection_run_id, collection_event_id


def record_validation_event(
    connection: Any,
    receipt: CollectionReceipt,
    *,
    validator_name: str,
    validator_version: str,
    status: str,
    issues: list[dict[str, Any]],
    draw_version_id: UUID | None = None,
    validated_at: datetime | None = None,
) -> UUID:
    if not validator_name.strip() or not validator_version.strip():
        raise ValueError("validator_name and validator_version cannot be empty")
    if status not in {"PASSED", "WARNING", "FAILED", "CONFLICT"}:
        raise ValueError("unsupported validation status")
    if not isinstance(issues, list):
        raise TypeError("issues must be a list")
    try:
        json.dumps(issues, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("issues must contain JSON-compatible values") from exc

    timestamp = validated_at or datetime.now(timezone.utc)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("validated_at must be timezone-aware")
    validation_event_id = uuid4()
    with connection.transaction():
        connection.execute(
            """INSERT INTO ingestion.validation_events
               (validation_event_id, collection_run_id, raw_object_id, draw_version_id,
                validator_name, validator_version, status, issues, validated_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                validation_event_id,
                receipt.collection_run_id,
                receipt.raw_object_id,
                draw_version_id,
                validator_name,
                validator_version,
                status,
                Jsonb(issues),
                timestamp.astimezone(timezone.utc),
            ),
        )
    return validation_event_id
