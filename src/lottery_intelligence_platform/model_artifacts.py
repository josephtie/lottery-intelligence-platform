"""Versioned trained-model artifact registry.

The current prospective cohort uses stateless models (statistics recomputed
per call, no serialized parameters) — this registry exists so a parametric
model entering a future cohort version is content-addressed and reproducible
from day one: the artifact bytes live in the raw object store under their
SHA-256 key, and `research.model_artifacts` (append-only) binds them to an
immutable model_version.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.raw import RawObjectStore


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    artifact_id: UUID
    model_version_id: UUID
    kind: str
    storage_uri: str
    sha256: str
    size_bytes: int
    metadata: Mapping[str, Any]


def register_artifact(
    connection: Any,
    store: RawObjectStore,
    *,
    model_version_id: UUID,
    kind: str,
    content: bytes,
    content_type: str = "application/octet-stream",
    metadata: Mapping[str, Any] | None = None,
) -> ModelArtifact:
    """Store `content` content-addressed and register it for `model_version_id`.

    Idempotent on (model_version_id, sha256): re-registering identical bytes
    returns the existing artifact.
    """
    if not kind.strip():
        raise ValueError("artifact kind must be non-empty")
    ref = store.put(content, content_type)
    artifact_id = uuid4()
    row = connection.execute(
        """INSERT INTO research.model_artifacts
               (artifact_id, model_version_id, kind, storage_uri, sha256,
                size_bytes, metadata)
           VALUES (%s, %s, %s, %s, %s, %s, %s)
           ON CONFLICT (model_version_id, sha256) DO NOTHING
           RETURNING artifact_id""",
        (
            artifact_id, model_version_id, kind, ref.object_key,
            ref.sha256, ref.byte_size, Jsonb(dict(metadata or {})),
        ),
    ).fetchone()
    if row is not None:
        artifact_id = row[0]
    else:
        artifact_id = connection.execute(
            """SELECT artifact_id FROM research.model_artifacts
               WHERE model_version_id = %s AND sha256 = %s""",
            (model_version_id, ref.sha256),
        ).fetchone()[0]
    return ModelArtifact(
        artifact_id=artifact_id,
        model_version_id=model_version_id,
        kind=kind,
        storage_uri=ref.object_key,
        sha256=ref.sha256,
        size_bytes=ref.byte_size,
        metadata=dict(metadata or {}),
    )


def resolve_artifact(connection: Any, artifact_id: UUID) -> ModelArtifact | None:
    row = connection.execute(
        """SELECT model_version_id, kind, storage_uri, sha256, size_bytes, metadata
           FROM research.model_artifacts WHERE artifact_id = %s""",
        (artifact_id,),
    ).fetchone()
    if row is None:
        return None
    return ModelArtifact(
        artifact_id=artifact_id,
        model_version_id=row[0], kind=row[1], storage_uri=row[2],
        sha256=row[3], size_bytes=row[4], metadata=row[5] or {},
    )


def latest_artifact(
    connection: Any, model_version_id: UUID, *, kind: str | None = None
) -> ModelArtifact | None:
    row = connection.execute(
        """SELECT artifact_id FROM research.model_artifacts
           WHERE model_version_id = %s AND (%s IS NULL OR kind = %s)
           ORDER BY created_at DESC LIMIT 1""",
        (model_version_id, kind, kind),
    ).fetchone()
    return resolve_artifact(connection, row[0]) if row else None


def verify_artifact_payload(artifact: ModelArtifact, payload: bytes) -> None:
    """Raise if fetched bytes do not match the registry's content hash."""
    digest = hashlib.sha256(payload).hexdigest()
    if digest != artifact.sha256:
        raise ValueError(
            f"artifact {artifact.artifact_id} integrity failure: "
            f"expected sha256 {artifact.sha256}, got {digest}"
        )


def artifact_manifest(artifact: ModelArtifact) -> str:
    """Canonical JSON line describing the artifact, for audit/reproducibility."""
    return json.dumps(
        {
            "artifact_id": str(artifact.artifact_id),
            "model_version_id": str(artifact.model_version_id),
            "kind": artifact.kind,
            "sha256": artifact.sha256,
            "size_bytes": artifact.size_bytes,
            "storage_uri": artifact.storage_uri,
        },
        sort_keys=True,
    )
