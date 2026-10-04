from __future__ import annotations

import hashlib
from pathlib import Path

from psycopg import ClientCursor


class MigrationChecksumError(RuntimeError):
    pass


def default_migrations_directory() -> Path:
    return Path(__file__).resolve().parents[2] / "infrastructure" / "postgres" / "migrations"


def apply_migrations(connection, migrations_directory: Path | None = None) -> list[str]:
    directory = migrations_directory or default_migrations_directory()
    migration_files = sorted(directory.glob("[0-9]*.sql"))
    applied: list[str] = []

    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(%s, %s)", (1_947_103_001, 1))
        for migration_file in migration_files:
            version = migration_file.stem
            sql = migration_file.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
            table_exists = connection.execute(
                "SELECT to_regclass('ops.schema_migrations') IS NOT NULL"
            ).fetchone()[0]

            existing = None
            if table_exists:
                existing = connection.execute(
                    "SELECT checksum_sha256 FROM ops.schema_migrations WHERE version = %s",
                    (version,),
                ).fetchone()

            if existing:
                if existing[0].strip() != checksum:
                    raise MigrationChecksumError(f"applied migration {version} has changed")
                continue

            ClientCursor(connection).execute(sql)
            table_exists = connection.execute(
                "SELECT to_regclass('ops.schema_migrations') IS NOT NULL"
            ).fetchone()[0]
            if not table_exists:
                raise RuntimeError(f"migration {version} did not create ops.schema_migrations")
            connection.execute(
                "INSERT INTO ops.schema_migrations (version, checksum_sha256) VALUES (%s, %s)",
                (version, checksum),
            )
            applied.append(version)

    return applied
