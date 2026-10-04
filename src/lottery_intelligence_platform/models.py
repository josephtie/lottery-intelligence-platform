from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from lottery_intelligence_platform.frequency_baseline import NUMBERS_MAX, NUMBERS_MIN

NUMBER_COUNT = NUMBERS_MAX - NUMBERS_MIN + 1
from lottery_intelligence_platform.research import canonical_sha256


@dataclass(frozen=True, slots=True)
class ModelVersion:
    model_version_id: UUID
    code: str
    family: str
    version: int
    definition_sha256: str
    created: bool


def register_model_version(
    connection: Any,
    *,
    code: str,
    family: str,
    definition: Mapping[str, Any],
) -> ModelVersion:
    if not code.strip():
        raise ValueError("model code cannot be empty")
    definition_sha = canonical_sha256(definition)
    with connection.transaction():
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (f"model:{code}",),
        )
        existing = connection.execute(
            """SELECT model_version_id, version FROM research.model_versions
               WHERE code = %s AND definition_sha256 = %s""",
            (code, definition_sha),
        ).fetchone()
        if existing:
            return ModelVersion(existing[0], code, family, existing[1], definition_sha, False)
        version = connection.execute(
            "SELECT COALESCE(MAX(version), 0) + 1 FROM research.model_versions WHERE code = %s",
            (code,),
        ).fetchone()[0]
        model_version_id = uuid4()
        connection.execute(
            """INSERT INTO research.model_versions
               (model_version_id, code, family, version, definition, definition_sha256)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (model_version_id, code, family, version, Jsonb(dict(definition)), definition_sha),
        )
        return ModelVersion(model_version_id, code, family, version, definition_sha, True)


def _ranked_by_score(counts: Sequence[int], scores: Sequence[float] | None = None) -> list[int]:
    values = scores if scores is not None else [float(c) for c in counts]
    return [
        index + NUMBERS_MIN
        for index, _ in sorted(enumerate(values), key=lambda item: (-item[1], item[0]))
    ]


def select_top_frequency(train_counts: Sequence[int], k: int) -> set[int]:
    return set(_ranked_by_score(train_counts)[:k])


def select_bayesian_shrinkage(
    train_counts: Sequence[int], k: int, *, alpha: float
) -> set[int]:
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    total = sum(train_counts) + alpha * len(train_counts)
    posterior = [(count + alpha) / total for count in train_counts]
    return set(_ranked_by_score(train_counts, posterior)[:k])


def select_uniform_reference(k: int, *, seed: int = 0) -> set[int]:
    rng = random.Random(seed)
    return set(rng.sample(range(NUMBERS_MIN, NUMBERS_MIN + NUMBER_COUNT), k))


SelectionModel = Callable[[Sequence[int], int], set[int]]


def selection_model_for(
    code: str,
    definition: Mapping[str, Any],
) -> SelectionModel:
    if code in {"top_k_frequency", "rolling_frequency"}:
        return lambda counts, k: select_top_frequency(counts, k)
    if code == "bayesian_shrinkage":
        alpha = float(definition.get("alpha", 1.0))
        return lambda counts, k: select_bayesian_shrinkage(counts, k, alpha=alpha)
    if code == "null_model_benchmark":
        seed = int(definition.get("seed", 0))
        return lambda counts, k: select_uniform_reference(k, seed=seed)
    raise ValueError(f"unknown selection model: {code}")
