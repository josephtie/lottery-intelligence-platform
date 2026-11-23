from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.collectors.lotobonheur import (
    CollectedBatch,
    ResultObservation,
    ScheduleObservation,
)


class DrawRegistryError(RuntimeError):
    pass


class UnmappedDrawTypeError(DrawRegistryError):
    pass


@dataclass(frozen=True, slots=True)
class ScheduleRegistration:
    draw_id: UUID
    schedule_version_id: UUID | None
    created: bool
    external_identity_conflict: bool


@dataclass(frozen=True, slots=True)
class ResultRegistration:
    draw_id: UUID
    draw_version_id: UUID
    canonical_draw_version_id: UUID | None
    status: str
    created: bool


class DrawRegistry:
    def __init__(
        self,
        connection: Any,
        *,
        game_id: UUID,
        game_version_id: UUID,
        source_id: UUID,
        draw_type_ids_by_name: Mapping[str, UUID] | None = None,
        auto_create_draw_types: bool = False,
    ) -> None:
        configured_types = dict(draw_type_ids_by_name or {})
        if not configured_types and not auto_create_draw_types:
            raise ValueError("configure draw types or enable auto_create_draw_types")
        if len(set(configured_types.values())) != len(configured_types):
            raise ValueError("each named Loto Bonheur session must map to a distinct draw type")
        if any(not name.strip() for name in configured_types):
            raise ValueError("draw type names cannot be empty")
        self._connection = connection
        self._game_id = game_id
        self._game_version_id = game_version_id
        self._source_id = source_id
        self._draw_type_ids = configured_types
        self._auto_create_draw_types = auto_create_draw_types

    def register_schedule_batch(
        self,
        batch: CollectedBatch[ScheduleObservation],
        *,
        observed_at: datetime | None = None,
    ) -> tuple[ScheduleRegistration, ...]:
        self._require_usable_batch(batch)
        if not batch.receipts:
            raise DrawRegistryError("schedule batch has no ingestion receipt")
        receipt = batch.receipts[-1]
        timestamp = _utc(observed_at or datetime.now(timezone.utc), "observed_at")
        registrations = []
        seen_identities: set[tuple[UUID, object]] = set()

        with self._connection.transaction():
            for observation in batch.validation.observations:
                draw_type_id = self._draw_type_id(observation.draw_name)
                identity = (draw_type_id, observation.group_date)
                if identity in seen_identities:
                    raise DrawRegistryError(
                        f"duplicate schedule identity for {observation.draw_name} on {observation.group_date}"
                    )
                seen_identities.add(identity)
                self._verify_draw_type(draw_type_id)
                draw_id = self._find_draw(
                    draw_type_id,
                    observation.group_date,
                    1,
                )
                external = self._connection.execute(
                    """SELECT draw_id, external_event_id
                       FROM core.draw_external_ids
                       WHERE source_id = %s AND external_draw_id = %s
                       FOR UPDATE""",
                    (self._source_id, observation.external_draw_id),
                ).fetchone()
                if external and (draw_id is None or external[0] != draw_id):
                    self._record_identity_conflict(
                        receipt.collection_event_id,
                        external[0],
                        observation,
                        "external draw id already maps to another logical draw",
                        timestamp,
                    )
                    registrations.append(ScheduleRegistration(external[0], None, False, True))
                    continue

                if draw_id is None:
                    draw_id, status = self._create_draw(
                        draw_type_id,
                        observation.group_date,
                        1,
                    )
                else:
                    status = self._draw_status(draw_id)

                event_identity_conflict = False
                if external is None:
                    self._connection.execute(
                        """INSERT INTO core.draw_external_ids
                           (draw_external_id, draw_id, source_id, external_draw_id,
                            external_event_id, first_seen_at, last_seen_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (
                            uuid4(), draw_id, self._source_id,
                            observation.external_draw_id, observation.external_event_id,
                            timestamp, timestamp,
                        ),
                    )
                else:
                    previous_event_id = external[1]
                    self._connection.execute(
                        """UPDATE core.draw_external_ids SET last_seen_at = %s,
                                  external_event_id = COALESCE(external_event_id, %s)
                           WHERE source_id = %s AND external_draw_id = %s""",
                        (timestamp, observation.external_event_id, self._source_id, observation.external_draw_id),
                    )
                    if previous_event_id and previous_event_id != observation.external_event_id:
                        event_identity_conflict = True
                        self._record_identity_conflict(
                            receipt.collection_event_id,
                            draw_id,
                            observation,
                            "external event id changed for a known external draw id",
                            timestamp,
                            previous_event_id=previous_event_id,
                        )

                if status == "SCHEDULED":
                    self._connection.execute(
                        "UPDATE core.draws SET status = 'EXPECTED' WHERE draw_id = %s",
                        (draw_id,),
                    )
                schedule_version_id, created = self._register_schedule_version(
                    draw_id,
                    receipt.raw_object_id,
                    observation,
                    timestamp,
                )
                registrations.append(
                    ScheduleRegistration(draw_id, schedule_version_id, created, event_identity_conflict)
                )
        return tuple(registrations)

    def register_result_batch(
        self,
        batch: CollectedBatch[ResultObservation],
        *,
        observed_at: datetime | None = None,
    ) -> tuple[ResultRegistration, ...]:
        self._require_usable_batch(batch)
        if not batch.receipts:
            raise DrawRegistryError("result batch has no ingestion receipt")
        receipt = batch.receipts[-1]
        timestamp = _utc(observed_at or datetime.now(timezone.utc), "observed_at")
        registrations = []

        with self._connection.transaction():
            for observation in batch.validation.observations:
                draw_type_id = self._draw_type_id(observation.draw_name)
                self._verify_draw_type(draw_type_id)
                draw_id = self._find_draw(draw_type_id, observation.draw_date, 1)
                if draw_id is None:
                    draw_id, status = self._create_draw(draw_type_id, observation.draw_date, 1)
                else:
                    status = self._draw_status(draw_id)

                canonical_version_id = self._canonical_version_id(draw_id)
                payload_hash = _result_payload_hash(observation)
                existing = self._connection.execute(
                    """SELECT draw_version_id, validation_status
                       FROM core.draw_versions
                       WHERE draw_id = %s AND payload_sha256 = %s""",
                    (draw_id, payload_hash),
                ).fetchone()
                if existing:
                    registrations.append(ResultRegistration(
                        draw_id,
                        existing[0],
                        canonical_version_id,
                        "UNCHANGED" if existing[0] == canonical_version_id else existing[1],
                        False,
                    ))
                    continue

                version_number = self._next_result_version(draw_id)
                draw_version_id = uuid4()
                is_correction = canonical_version_id is not None
                validation_status = "CONFLICT" if is_correction else "VALID"
                self._connection.execute(
                    """INSERT INTO core.draw_versions
                       (draw_version_id, draw_id, version_number, source_id, raw_object_id,
                        payload_sha256, result_observed_at, validated_at, confirmed_at,
                        validation_status, correction_reason, result_metadata)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        draw_version_id,
                        draw_id,
                        version_number,
                        self._source_id,
                        receipt.raw_object_id,
                        payload_hash,
                        timestamp,
                        None if is_correction else timestamp,
                        None if is_correction else timestamp,
                        validation_status,
                        "source result changed; reconciliation required" if is_correction else None,
                        Jsonb({
                            "draw_name": observation.draw_name,
                            "result_group": observation.result_group,
                            "source_date": observation.source_date,
                        }),
                    ),
                )
                self._insert_draw_numbers(draw_version_id, observation)

                if is_correction:
                    self._connection.execute(
                        """INSERT INTO core.draw_corrections
                           (draw_correction_id, draw_id, old_draw_version_id,
                            new_draw_version_id, reason, source_id, detected_at)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (
                            uuid4(), draw_id, canonical_version_id, draw_version_id,
                            "source result changed; reconciliation required",
                            self._source_id, timestamp,
                        ),
                    )
                    if status != "CORRECTED":
                        self._connection.execute(
                            "UPDATE core.draws SET status = 'CORRECTED' WHERE draw_id = %s",
                            (draw_id,),
                        )
                    registrations.append(ResultRegistration(
                        draw_id, draw_version_id, canonical_version_id, "CONFLICT", True
                    ))
                    continue

                self._freeze_draw(draw_id, status, draw_version_id)
                registrations.append(ResultRegistration(
                    draw_id, draw_version_id, draw_version_id, "FROZEN", True
                ))
        return tuple(registrations)

    def _draw_type_id(self, draw_name: str) -> UUID:
        configured = self._draw_type_ids.get(draw_name)
        if configured is not None:
            return configured
        existing = self._connection.execute(
            """SELECT draw_type_id FROM catalog.draw_types
               WHERE game_version_id = %s AND display_name = %s""",
            (self._game_version_id, draw_name),
        ).fetchone()
        if existing:
            self._draw_type_ids[draw_name] = existing[0]
            return existing[0]
        if not self._auto_create_draw_types:
            raise UnmappedDrawTypeError(f"no catalog draw type is configured for {draw_name!r}")

        normalized = unicodedata.normalize("NFKD", draw_name).encode("ascii", "ignore").decode("ascii")
        base_code = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
        if not base_code:
            raise UnmappedDrawTypeError(f"draw name cannot be normalized to a catalog code: {draw_name!r}")
        code = base_code
        collision = self._connection.execute(
            """SELECT display_name FROM catalog.draw_types
               WHERE game_version_id = %s AND code = %s""",
            (self._game_version_id, code),
        ).fetchone()
        if collision and collision[0] != draw_name:
            code = f"{base_code}_{hashlib.sha256(draw_name.encode('utf-8')).hexdigest()[:8]}"
        draw_type_id = uuid4()
        self._connection.execute(
            """INSERT INTO catalog.draw_types
               (draw_type_id, game_version_id, code, display_name, rules)
               VALUES (%s, %s, %s, %s, %s)""",
            (
                draw_type_id,
                self._game_version_id,
                code,
                draw_name,
                Jsonb({
                    "source_draw_name": draw_name,
                    "catalog_discovery": "OFFICIAL_RESULT_SOURCE",
                    "modeling_eligibility": "REVIEW_REQUIRED",
                }),
            ),
        )
        self._draw_type_ids[draw_name] = draw_type_id
        return draw_type_id

    def _verify_draw_type(self, draw_type_id: UUID) -> None:
        row = self._connection.execute(
            "SELECT 1 FROM catalog.draw_types WHERE draw_type_id = %s AND game_version_id = %s",
            (draw_type_id, self._game_version_id),
        ).fetchone()
        if row is None:
            raise UnmappedDrawTypeError("draw type does not belong to the configured game version")

    def _find_draw(self, draw_type_id: UUID, scheduled_date: Any, sequence: int) -> UUID | None:
        row = self._connection.execute(
            """SELECT draw_id FROM core.draws
               WHERE game_version_id = %s AND draw_type_id = %s
                 AND scheduled_date = %s AND scheduled_sequence = %s
               FOR UPDATE""",
            (self._game_version_id, draw_type_id, scheduled_date, sequence),
        ).fetchone()
        return row[0] if row else None

    def _create_draw(self, draw_type_id: UUID, scheduled_date: Any, sequence: int) -> tuple[UUID, str]:
        draw_id = uuid4()
        inserted = self._connection.execute(
            """INSERT INTO core.draws
               (draw_id, game_id, game_version_id, draw_type_id,
                scheduled_date, scheduled_sequence)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT (game_version_id, draw_type_id, scheduled_date, scheduled_sequence)
               DO NOTHING
               RETURNING draw_id, status""",
            (draw_id, self._game_id, self._game_version_id, draw_type_id, scheduled_date, sequence),
        ).fetchone()
        if inserted:
            return inserted[0], inserted[1]
        existing = self._connection.execute(
            """SELECT draw_id, status FROM core.draws
               WHERE game_version_id = %s AND draw_type_id = %s
                 AND scheduled_date = %s AND scheduled_sequence = %s
               FOR UPDATE""",
            (self._game_version_id, draw_type_id, scheduled_date, sequence),
        ).fetchone()
        if existing is None:
            raise DrawRegistryError("logical draw disappeared during registration")
        return existing[0], existing[1]

    def _draw_status(self, draw_id: UUID) -> str:
        return self._connection.execute(
            "SELECT status FROM core.draws WHERE draw_id = %s FOR UPDATE",
            (draw_id,),
        ).fetchone()[0]

    def _canonical_version_id(self, draw_id: UUID) -> UUID | None:
        return self._connection.execute(
            "SELECT canonical_draw_version_id FROM core.draws WHERE draw_id = %s FOR UPDATE",
            (draw_id,),
        ).fetchone()[0]

    def _next_result_version(self, draw_id: UUID) -> int:
        return self._connection.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM core.draw_versions WHERE draw_id = %s",
            (draw_id,),
        ).fetchone()[0]

    def _insert_draw_numbers(self, draw_version_id: UUID, observation: ResultObservation) -> None:
        rows = [(draw_version_id, "WINNING", position, number)
                for position, number in enumerate(observation.winning_numbers, 1)]
        if observation.machine_numbers is not None:
            rows.extend(
                (draw_version_id, "MACHINE", position, number)
                for position, number in enumerate(observation.machine_numbers, 1)
            )
        self._connection.cursor().executemany(
            "INSERT INTO core.draw_numbers (draw_version_id, number_role, position, number) VALUES (%s, %s, %s, %s)",
            rows,
        )

    def _freeze_draw(self, draw_id: UUID, status: str, draw_version_id: UUID) -> None:
        transitions = {
            "SCHEDULED": "DETECTED",
            "EXPECTED": "DETECTED",
            "MISSING": "DETECTED",
            "DELAYED": "DETECTED",
            "INVALID": "DETECTED",
            "DETECTED": "VALIDATING",
            "CONFLICT": "VALIDATING",
            "CORRECTED": "VALIDATING",
            "DISPUTED": "VALIDATING",
            "VALIDATING": "VALIDATED",
            "VALIDATED": "CONFIRMED",
            "CONFIRMED": "FROZEN",
        }
        current = status
        while current != "FROZEN":
            next_status = transitions.get(current)
            if next_status is None:
                raise DrawRegistryError(f"cannot freeze a draw from status {current}")
            self._connection.execute(
                "UPDATE core.draws SET status = %s WHERE draw_id = %s",
                (next_status, draw_id),
            )
            current = next_status
        self._connection.execute(
            "UPDATE core.draws SET canonical_draw_version_id = %s WHERE draw_id = %s",
            (draw_version_id, draw_id),
        )

    def _register_schedule_version(
        self,
        draw_id: UUID,
        raw_object_id: UUID,
        observation: ScheduleObservation,
        observed_at: datetime,
    ) -> tuple[UUID, bool]:
        payload = json.dumps(observation.source_data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        existing = self._connection.execute(
            "SELECT draw_schedule_version_id FROM core.draw_schedule_versions WHERE draw_id = %s AND payload_sha256 = %s",
            (draw_id, payload_hash),
        ).fetchone()
        if existing:
            return existing[0], False
        version_number = self._connection.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 FROM core.draw_schedule_versions WHERE draw_id = %s",
            (draw_id,),
        ).fetchone()[0]
        version_id = uuid4()
        self._connection.execute(
            """INSERT INTO core.draw_schedule_versions
               (draw_schedule_version_id, draw_id, version_number, source_id, raw_object_id,
                source_datetime, source_timezone, scheduled_at, payload_sha256, observed_at, schedule_data)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                version_id, draw_id, version_number, self._source_id, raw_object_id,
                observation.source_datetime, observation.source_timezone,
                observation.scheduled_at, payload_hash, observed_at, Jsonb(observation.source_data),
            ),
        )
        return version_id, True

    def _record_identity_conflict(
        self,
        collection_event_id: UUID,
        draw_id: UUID,
        observation: ScheduleObservation,
        reason: str,
        occurred_at: datetime,
        previous_event_id: str | None = None,
    ) -> None:
        details = {
            "reason": reason,
            "external_draw_id": observation.external_draw_id,
            "observed_event_id": observation.external_event_id,
            "draw_name": observation.draw_name,
            "scheduled_at": observation.source_datetime,
        }
        if previous_event_id is not None:
            details["previous_event_id"] = previous_event_id
        self._connection.execute(
            """INSERT INTO ingestion.ingestion_events
               (ingestion_event_id, collection_event_id, event_type, subject_type,
                subject_id, details, occurred_at)
               VALUES (%s, %s, 'DRAW_EXTERNAL_ID_CONFLICT', 'draw', %s, %s, %s)""",
            (uuid4(), collection_event_id, draw_id, Jsonb(details), occurred_at),
        )

    @staticmethod
    def _require_usable_batch(batch: CollectedBatch[Any]) -> None:
        if batch.validation.status not in {"PASSED", "WARNING"}:
            raise DrawRegistryError("only passed or warning-level source batches can enter the registry")


def _result_payload_hash(observation: ResultObservation) -> str:
    content = {
        "draw_date": observation.draw_date.isoformat(),
        "draw_name": observation.draw_name,
        "result_group": observation.result_group,
        "winning_numbers": list(observation.winning_numbers),
        "machine_numbers": list(observation.machine_numbers) if observation.machine_numbers is not None else None,
    }
    payload = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value.astimezone(timezone.utc)
